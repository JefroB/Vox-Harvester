"""Patch mode engine for surgical file edits.

Parses SEARCH/REPLACE edit operations from model responses and applies
them to target files without full regeneration.
"""

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# Markers: 7 angle brackets + keyword
SEARCH_MARKER = "<<<<<<< SEARCH"
SEPARATOR_MARKER = "======="
REPLACE_MARKER = ">>>>>>> REPLACE"


@dataclass
class EditOperation:
    """A single search-and-replace edit operation."""

    old_text: str
    new_text: str
    index: int  # 0-based position in the sequence


class _ParserState:
    """State machine states for parsing edit operations."""

    NORMAL = "NORMAL"
    IN_SEARCH = "IN_SEARCH"
    IN_REPLACE = "IN_REPLACE"


def parse_edit_operations(response: str) -> list[EditOperation]:
    """Parse model response into edit operations.

    Uses a line-by-line state machine with three states:
    - NORMAL: scanning for <<<<<<< SEARCH marker
    - IN_SEARCH: collecting old_text lines until ======= separator
    - IN_REPLACE: collecting new_text lines until >>>>>>> REPLACE marker

    Returns list of EditOperation, or empty list if no markers found.
    Incomplete operations (missing closing REPLACE marker) are discarded.
    """
    operations: list[EditOperation] = []
    state = _ParserState.NORMAL
    search_lines: list[str] = []
    replace_lines: list[str] = []
    operation_index = 0

    for line in response.splitlines(keepends=True):
        stripped = line.rstrip("\n").rstrip("\r")

        if state == _ParserState.NORMAL:
            if stripped == SEARCH_MARKER:
                state = _ParserState.IN_SEARCH
                search_lines = []
                replace_lines = []

        elif state == _ParserState.IN_SEARCH:
            if stripped == SEPARATOR_MARKER:
                state = _ParserState.IN_REPLACE
            else:
                search_lines.append(line)

        elif state == _ParserState.IN_REPLACE:
            if stripped == REPLACE_MARKER:
                # Emit completed operation
                old_text = "".join(search_lines)
                new_text = "".join(replace_lines)
                # Strip trailing newline from last line if present
                # to avoid double-newline when joining
                if old_text.endswith("\n"):
                    old_text = old_text[:-1]
                if new_text.endswith("\n"):
                    new_text = new_text[:-1]
                operations.append(
                    EditOperation(
                        old_text=old_text,
                        new_text=new_text,
                        index=operation_index,
                    )
                )
                operation_index += 1
                state = _ParserState.NORMAL
            else:
                replace_lines.append(line)

    # Incomplete operations (state != NORMAL at end) are silently discarded
    return operations


def apply_edit_operations(file_path: Path, operations: list[EditOperation]) -> tuple[int, int]:
    """Apply edits sequentially to file.

    Returns (applied_count, skipped_count).
    Each old_text must match character-for-character (whitespace-sensitive).
    Non-matching edits are skipped with a warning.
    """
    content = file_path.read_text(encoding="utf-8")
    applied_count = 0
    skipped_count = 0

    for op in operations:
        if op.old_text in content:
            content = content.replace(op.old_text, op.new_text, 1)
            applied_count += 1
        else:
            # Build preview: first 5 lines of old_text
            preview_lines = op.old_text.splitlines()[:5]
            preview = "\n".join(preview_lines)
            print(
                f"[WARN] patch: Edit operation {op.index} failed — "
                f"old_text not found in target file {file_path}",
                file=sys.stderr,
            )
            skipped_count += 1

    # Write modified content back
    file_path.write_text(content, encoding="utf-8")

    return (applied_count, skipped_count)


class SymbolNotFoundError(Exception):
    """Raised when codesearch cannot find the requested symbol."""

    def __init__(self, symbol_name: str) -> None:
        self.symbol_name = symbol_name
        super().__init__(f"Symbol not found: {symbol_name}")


# Pattern to match codesearch header line, e.g.:
# "// File: path.py, Lines: 10-50"
_CODESEARCH_HEADER_PATTERN = re.compile(
    r"^//\s*File:\s*.+,\s*Lines:\s*(\d+)-(\d+)\s*$"
)


def extract_symbol_context(symbol_name: str) -> tuple[str, int, int]:
    """Use CodeSearch to get symbol implementation.

    Calls `codesearch get-symbol-code <name>` and parses the output.

    Returns:
        Tuple of (source_code, start_line, end_line).

    Raises:
        SymbolNotFoundError: If codesearch returns no result or a non-zero exit code.
    """
    result = subprocess.run(
        ["codesearch", "get-symbol-code", symbol_name],
        capture_output=True,
        text=True,
    )

    # Non-zero exit code means symbol not found or codesearch error
    if result.returncode != 0:
        raise SymbolNotFoundError(symbol_name)

    output = result.stdout.strip()

    # Empty output means no result
    if not output:
        raise SymbolNotFoundError(symbol_name)

    # Parse the output: first line is a header with file path and line range,
    # remaining lines are the source code
    lines = output.split("\n")

    # Try to match the header pattern on the first line
    header_match = _CODESEARCH_HEADER_PATTERN.match(lines[0])
    if not header_match:
        # No recognizable header — treat entire output as source with unknown lines
        raise SymbolNotFoundError(symbol_name)

    start_line = int(header_match.group(1))
    end_line = int(header_match.group(2))

    # Source code is everything after the header line
    source_code = "\n".join(lines[1:])

    return (source_code, start_line, end_line)


def calculate_timeout(context_tokens: int) -> int:
    """Auto-scale timeout based on context size.

    Formula: 60s base + 3s per 100 tokens of context, capped at 600s.
    Result is always in the range [60, 600].

    Args:
        context_tokens: Non-negative integer representing the number of
            context tokens being sent to the model.

    Returns:
        Timeout in seconds, between 60 and 600 inclusive.
    """
    return min(60 + (context_tokens // 100) * 3, 600)
