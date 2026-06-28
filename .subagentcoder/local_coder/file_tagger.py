"""
File Tagger — CodeSearch-based file and symbol resolution.

Automatically resolves symbol names and file paths referenced in task descriptions
to precise file + line-range references via the CodeSearch index.

Strategy:
1. Extract candidate symbols (CamelCase, snake_case identifiers)
2. Extract candidate file paths (slash-separated tokens, extensions)
3. Query `codesearch search <symbol>` for each candidate
4. Verify file existence for path candidates
5. Deduplicate and cap at 5 results

The file tagger is non-fatal: if CodeSearch is unavailable or any query fails,
it logs a warning and returns partial or empty results.
"""

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Maximum number of file tags returned per task
MAX_FILE_TAGS = 5

# Subprocess timeout in seconds
SUBPROCESS_TIMEOUT = 5

# Common source file extensions for path detection
_SOURCE_EXTENSIONS = {
    ".py", ".ts", ".js", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".vue", ".svelte", ".html", ".css", ".scss",
    ".sql", ".sh", ".bash", ".ps1", ".yaml", ".yml", ".toml",
    ".json", ".xml", ".md", ".txt", ".cfg", ".ini", ".conf",
}

# Regex patterns for symbol extraction
_CAMEL_CASE_RE = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z]+)+")
_SNAKE_CASE_RE = re.compile(r"\b[a-z_][a-z0-9_]{2,}\b")

# File path pattern: tokens containing / or \ with a file extension
_FILE_PATH_RE = re.compile(
    r"(?:[a-zA-Z0-9_\-./\\]+[/\\][a-zA-Z0-9_\-./\\]*\.[a-zA-Z]{1,10})"
)

# Words to exclude from snake_case matches (too common, too short, or noise)
_SNAKE_CASE_EXCLUSIONS = {
    "the", "and", "for", "not", "you", "all", "can", "has", "its",
    "new", "now", "old", "our", "out", "own", "say", "she", "too",
    "use", "way", "who", "how", "man", "did", "get", "let", "may",
    "see", "set", "try", "was", "ask", "end", "far", "few", "got",
    "had", "her", "him", "his", "put", "run", "top", "yet",
    "with", "this", "that", "from", "have", "will", "been", "each",
    "make", "like", "long", "look", "many", "some", "than", "them",
    "then", "very", "when", "come", "here", "just", "know", "take",
    "want", "does", "into", "more", "only", "over", "such", "what",
    "also", "back", "much", "must", "name", "same", "tell", "time",
    "true", "false", "none", "null", "self", "args", "kwargs",
}


@dataclass
class FileTag:
    """A reference to a file path with an optional line range."""

    file_path: str
    line_range: tuple[int, int] | None = None


def _log_warning(message: str) -> None:
    """Log a warning message to stderr with FILE-TAG prefix."""
    print(f"[FILE-TAG] {message}", file=sys.stderr)


def is_codesearch_available(workspace_root: Path) -> bool:
    """Check if .codesearch/index.db exists and codesearch command responds.

    Args:
        workspace_root: Root directory of the workspace.

    Returns:
        True if CodeSearch index exists, False otherwise.
    """
    index_path = workspace_root / ".codesearch" / "index.db"
    return index_path.exists()


def _extract_camel_case_symbols(task: str) -> list[str]:
    """Extract CamelCase identifiers from the task description.

    Pattern: [A-Z][a-z]+(?:[A-Z][a-z]+)+ — requires at least two humps.
    """
    return _CAMEL_CASE_RE.findall(task)


def _extract_snake_case_symbols(task: str) -> list[str]:
    """Extract snake_case identifiers from the task description.

    Pattern: [a-z_][a-z0-9_]{2,} — minimum 3 chars to avoid noise.
    Filters out common English words.
    """
    matches = _SNAKE_CASE_RE.findall(task)
    # Filter out common words and require at least one underscore or
    # be obviously a code identifier (starts with underscore)
    results = []
    for match in matches:
        if match in _SNAKE_CASE_EXCLUSIONS:
            continue
        # Require underscore to distinguish from regular words
        if "_" in match or match.startswith("_"):
            results.append(match)
    return results


def _extract_file_paths(task: str) -> list[str]:
    """Extract file path candidates from the task description.

    Looks for tokens containing / or \\ with common file extensions.
    """
    matches = _FILE_PATH_RE.findall(task)
    results = []
    for match in matches:
        # Normalize path separators
        normalized = match.replace("\\", "/")
        # Check if it ends with a known extension
        _, ext = os.path.splitext(normalized)
        if ext.lower() in _SOURCE_EXTENSIONS:
            results.append(normalized)
    return results


def _query_codesearch(symbol: str, workspace_root: Path) -> FileTag | None:
    """Query CodeSearch for a symbol and parse the result.

    Args:
        symbol: The symbol name to search for.
        workspace_root: Root directory of the workspace.

    Returns:
        A FileTag if the symbol was found, None otherwise.
    """
    try:
        result = subprocess.run(
            ["codesearch", "search", symbol],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            cwd=str(workspace_root),
        )

        if result.returncode != 0:
            return None

        output = result.stdout.strip()
        if not output:
            return None

        # Parse codesearch output — typically: file_path:line_number
        # Take the first result line
        first_line = output.split("\n")[0].strip()
        if not first_line:
            return None

        # Try to parse "file_path:line" or "file_path:line:column" format
        parts = first_line.split(":")

        if len(parts) >= 2:
            file_path = parts[0]
            try:
                line_num = int(parts[1])
                # Create a small range around the line (± 10 lines)
                start_line = max(1, line_num - 5)
                end_line = line_num + 15
                # Verify the file exists
                full_path = workspace_root / file_path
                if full_path.exists():
                    return FileTag(
                        file_path=str(full_path),
                        line_range=(start_line, end_line),
                    )
            except (ValueError, IndexError):
                pass

            # If we can't parse the line number, just use the file path
            full_path = workspace_root / file_path
            if full_path.exists():
                return FileTag(file_path=str(full_path))

        # Might just be a file path without line info
        potential_path = workspace_root / first_line
        if potential_path.exists():
            return FileTag(file_path=str(potential_path))

        return None

    except subprocess.TimeoutExpired:
        _log_warning(f"CodeSearch query timed out for symbol: {symbol}")
        return None
    except (OSError, subprocess.SubprocessError) as e:
        _log_warning(f"CodeSearch query failed for symbol '{symbol}': {e}")
        return None


def _verify_file_path(path: str, workspace_root: Path) -> FileTag | None:
    """Verify that a file path exists and return a FileTag.

    Tries both relative-to-workspace and absolute interpretations.

    Args:
        path: The file path to verify.
        workspace_root: Root directory of the workspace.

    Returns:
        A FileTag if the file exists, None otherwise.
    """
    # Try relative to workspace root
    full_path = workspace_root / path
    if full_path.exists() and full_path.is_file():
        return FileTag(file_path=str(full_path))

    # Try as absolute path
    abs_path = Path(path)
    if abs_path.is_absolute() and abs_path.exists() and abs_path.is_file():
        return FileTag(file_path=str(abs_path))

    return None


def tag_files(task: str, workspace_root: Path) -> list[FileTag]:
    """Query CodeSearch to resolve symbols/paths in task description.

    Strategy:
    1. Extract candidate symbols (CamelCase, snake_case identifiers)
    2. Extract candidate file paths (slash-separated tokens, extensions)
    3. Query `codesearch search <symbol>` for each candidate
    4. Verify file existence for path candidates
    5. Deduplicate and cap at 5 results

    Args:
        task: The task description to extract references from.
        workspace_root: Root directory of the workspace.

    Returns:
        list of FileTag (max 5). Empty list if CodeSearch is unavailable
        or no references could be resolved.
    """
    if not is_codesearch_available(workspace_root):
        _log_warning("CodeSearch unavailable, skipping file tagging")
        return []

    results: list[FileTag] = []
    seen_paths: set[str] = set()

    def _add_tag(tag: FileTag | None) -> None:
        """Add a tag if not None and not a duplicate."""
        if tag is None:
            return
        if tag.file_path in seen_paths:
            return
        seen_paths.add(tag.file_path)
        results.append(tag)

    # 1. Extract and resolve file path candidates first (most specific)
    file_paths = _extract_file_paths(task)
    for path in file_paths:
        if len(results) >= MAX_FILE_TAGS:
            break
        tag = _verify_file_path(path, workspace_root)
        _add_tag(tag)

    # 2. Extract and query CamelCase symbols
    camel_symbols = _extract_camel_case_symbols(task)
    for symbol in camel_symbols:
        if len(results) >= MAX_FILE_TAGS:
            break
        tag = _query_codesearch(symbol, workspace_root)
        _add_tag(tag)

    # 3. Extract and query snake_case symbols
    snake_symbols = _extract_snake_case_symbols(task)
    for symbol in snake_symbols:
        if len(results) >= MAX_FILE_TAGS:
            break
        tag = _query_codesearch(symbol, workspace_root)
        _add_tag(tag)

    return results[:MAX_FILE_TAGS]
