"""Scope enforcer for constraining local coder modifications.

Parses scope strings into structured entries (symbol names, line ranges,
or natural-language descriptions) and provides validation utilities to
ensure edits stay within declared boundaries.
"""

from __future__ import annotations

import difflib
import re
import sys
from dataclasses import dataclass

# Maximum allowed length for a scope string (Requirement 7.1)
MAX_SCOPE_LENGTH = 500

# Pattern for valid symbol names: identifier with optional dot-separated parts
# e.g. 'validate_email', 'MyClass.method', 'a.b.c'
_SYMBOL_PATTERN = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$"
)

# Pattern for line ranges: digits-digits (e.g. '10-50', '100-200')
_LINE_RANGE_PATTERN = re.compile(r"^\d+-\d+$")


@dataclass
class ScopeEntry:
    """A single scope boundary.

    Attributes:
        kind: The type of scope entry — "symbol", "line_range", or "description".
        value: The raw string value of the entry (stripped of surrounding whitespace).
        start_line: Start line number for line_range entries, None otherwise.
        end_line: End line number for line_range entries, None otherwise.
    """

    kind: str  # "symbol" | "line_range" | "description"
    value: str
    start_line: int | None = None
    end_line: int | None = None


def parse_scope(scope_str: str) -> list[ScopeEntry]:
    """Parse scope string into structured entries.

    Splits on commas, strips whitespace, then classifies each entry:
    - Symbol names: match `^[a-zA-Z_][a-zA-Z0-9_]*(\\.[a-zA-Z_][a-zA-Z0-9_]*)*$`
    - Line ranges: match `^\\d+-\\d+$`
    - Natural-language: anything else (passed to prompt as-is)

    Args:
        scope_str: Comma-separated scope description string.

    Returns:
        List of ScopeEntry objects representing each parsed scope boundary.

    Raises:
        ValueError: If scope_str exceeds 500 characters.
    """
    if len(scope_str) > MAX_SCOPE_LENGTH:
        raise ValueError(
            f"scope string must be at most {MAX_SCOPE_LENGTH} characters, "
            f"got {len(scope_str)}"
        )

    entries: list[ScopeEntry] = []

    for raw_entry in scope_str.split(","):
        entry = raw_entry.strip()
        if not entry:
            # Skip empty entries (e.g. trailing comma or double comma)
            continue

        if _LINE_RANGE_PATTERN.match(entry):
            # Line range: "10-50" → start=10, end=50
            parts = entry.split("-")
            start_line = int(parts[0])
            end_line = int(parts[1])
            entries.append(
                ScopeEntry(
                    kind="line_range",
                    value=entry,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
        elif _SYMBOL_PATTERN.match(entry):
            # Symbol name: "validate_email", "MyClass.method"
            entries.append(ScopeEntry(kind="symbol", value=entry))
        else:
            # Natural-language description: anything else
            entries.append(ScopeEntry(kind="description", value=entry))

    return entries


def _find_edit_line_range(old_text: str, file_content: str) -> tuple[int, int] | None:
    """Find the line range where old_text occurs in file_content.

    Returns (start_line, end_line) as 1-based line numbers, or None if not found.
    """
    idx = file_content.find(old_text)
    if idx == -1:
        return None

    # Count lines before the match start to get start_line (1-based)
    start_line = file_content[:idx].count("\n") + 1

    # Count newlines within old_text to get end_line
    lines_in_edit = old_text.count("\n")
    end_line = start_line + lines_in_edit

    return (start_line, end_line)


def _overlaps_line_range(
    edit_start: int, edit_end: int, scope_start: int, scope_end: int
) -> bool:
    """Check if two line ranges overlap (inclusive on both ends)."""
    return edit_start <= scope_end and edit_end >= scope_start


def _edit_overlaps_scope(
    edit_start: int,
    edit_end: int,
    old_text: str,
    scope: list[ScopeEntry],
) -> bool:
    """Check if an edit overlaps with any scope entry.

    For line_range entries: check line overlap.
    For symbol entries: check if old_text contains the symbol name (heuristic).
    For description entries: always allow (can't validate natural-language).
    """
    for entry in scope:
        if entry.kind == "line_range":
            assert entry.start_line is not None and entry.end_line is not None
            if _overlaps_line_range(
                edit_start, edit_end, entry.start_line, entry.end_line
            ):
                return True
        elif entry.kind == "symbol":
            # Heuristic: check if old_text contains the symbol name
            if entry.value in old_text:
                return True
        elif entry.kind == "description":
            # Natural-language descriptions can't be programmatically validated;
            # always allow edits when description scope is present.
            return True

    return False


def validate_edits_against_scope(
    operations: "list[EditOperation]",
    scope: list[ScopeEntry],
    file_content: str,
) -> "tuple[list[EditOperation], list[EditOperation]]":
    """Partition edits into in-scope and out-of-scope.

    For each edit operation:
    1. Find where old_text occurs in file_content (line range).
    2. Check if that line range overlaps with any scope entry.
    3. If overlaps → allowed. If not → rejected with stderr warning.

    Returns (allowed_edits, rejected_edits).
    """
    # Avoid circular import at module level
    from local_coder.patch_mode import EditOperation  # noqa: F811

    allowed: list[EditOperation] = []
    rejected: list[EditOperation] = []

    # Build a string representation of the full scope for warning messages
    scope_str = ", ".join(entry.value for entry in scope)

    for op in operations:
        line_range = _find_edit_line_range(op.old_text, file_content)

        if line_range is None:
            # old_text not found in file — treat as out-of-scope
            # (it can't be validated positionally)
            print(
                f"[WARN] scope: Rejected edit {op.index} "
                f"(old_text not found in file, cannot validate scope)",
                file=sys.stderr,
            )
            rejected.append(op)
            continue

        edit_start, edit_end = line_range

        if _edit_overlaps_scope(edit_start, edit_end, op.old_text, scope):
            allowed.append(op)
        else:
            print(
                f'[WARN] scope: Rejected edit at lines {edit_start}-{edit_end} '
                f'(outside scope "{scope_str}")',
                file=sys.stderr,
            )
            rejected.append(op)

    return (allowed, rejected)


def _get_changed_line_ranges(original: str, new_content: str) -> list[tuple[int, int]]:
    """Diff original vs new content and return changed line ranges.

    Uses difflib.unified_diff to identify lines that were added, removed,
    or modified. Returns a list of (start_line, end_line) tuples (1-based)
    representing contiguous ranges of changed lines in the new content.
    """
    original_lines = original.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Get opcodes from SequenceMatcher — these describe blocks of changes
    matcher = difflib.SequenceMatcher(None, original_lines, new_lines)

    ranges: list[tuple[int, int]] = []

    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        # For 'replace', 'insert', 'delete' — record the affected lines
        # in the *new* content (j1, j2 are 0-based indices into new_lines)
        if tag == "delete":
            # Lines were deleted — the change point is at the line in the new
            # file where the deletion happened. Map to surrounding context.
            # Use j1+1 as the line number (1-based), representing where
            # the deleted content used to be adjacent to.
            if j1 > 0:
                ranges.append((j1, j1))  # 1-based: j1 is already the right ref
            else:
                ranges.append((1, 1))
        else:
            # 'replace' or 'insert': lines j1..j2-1 in new content are changed
            # Convert to 1-based inclusive range
            start = j1 + 1
            end = j2  # j2 is exclusive in 0-based, so j2 = inclusive end in 1-based
            ranges.append((start, end))

    # Merge overlapping/adjacent ranges
    if not ranges:
        return []

    ranges.sort()
    merged: list[tuple[int, int]] = [ranges[0]]
    for start, end in ranges[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            # Overlapping or adjacent — merge
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def _change_overlaps_scope(
    change_start: int,
    change_end: int,
    new_lines: list[str],
    scope: list[ScopeEntry],
) -> bool:
    """Check if a changed line range overlaps with any scope entry.

    For line_range entries: direct overlap check.
    For symbol entries: check if the changed lines OR nearby preceding lines
        contain the symbol name (heuristic — the change is likely inside the
        function/class whose definition precedes it).
    For description entries: always consider in-scope (can't validate NL).
    """
    for entry in scope:
        if entry.kind == "line_range":
            assert entry.start_line is not None and entry.end_line is not None
            if _overlaps_line_range(
                change_start, change_end, entry.start_line, entry.end_line
            ):
                return True
        elif entry.kind == "symbol":
            # Check if any of the changed lines contain the symbol name
            # change_start/end are 1-based, new_lines is 0-based
            for line_idx in range(change_start - 1, min(change_end, len(new_lines))):
                if entry.value in new_lines[line_idx]:
                    return True
            # Also scan backwards from the change start to find a preceding
            # definition line containing the symbol name. This handles the
            # common case where a change is inside a function body but the
            # symbol name only appears on the def/class line above.
            scan_start = max(0, change_start - 2)  # 0-based index before change
            for line_idx in range(scan_start, -1, -1):
                if entry.value in new_lines[line_idx]:
                    return True
                # Stop scanning if we hit an empty line or another def/class —
                # that suggests we've left the enclosing scope.
                stripped = new_lines[line_idx].strip()
                if stripped == "":
                    break
        elif entry.kind == "description":
            # Natural-language descriptions can't be validated;
            # always consider in-scope.
            return True

    return False


def detect_out_of_scope_changes(
    original: str,
    new_content: str,
    scope: list[ScopeEntry],
) -> list[str]:
    """Compare original and new content, identify changes outside scope.

    Used in non-patch mode (advisory enforcement). Diffs the original file
    against the new output and checks each changed region against the scope
    definition.

    Args:
        original: The original file content. If empty string, this is treated
            as a new file and validation is skipped entirely (Req 7.7).
        new_content: The new file content produced by the model.
        scope: Parsed scope entries defining allowed modification boundaries.

    Returns:
        List of warning messages for out-of-scope changes. Each message
        describes the line range of the violation. Returns empty list if
        all changes are within scope or if this is a new file.
    """
    # Skip validation for new files (original doesn't exist / is empty)
    if not original:
        return []

    # Find all changed line ranges
    changed_ranges = _get_changed_line_ranges(original, new_content)

    if not changed_ranges:
        return []

    # Split new_content into lines for symbol checking
    new_lines = new_content.splitlines()

    warnings: list[str] = []

    for change_start, change_end in changed_ranges:
        if not _change_overlaps_scope(change_start, change_end, new_lines, scope):
            warnings.append(
                f"Lines {change_start}-{change_end}: changes outside declared scope"
            )

    return warnings
