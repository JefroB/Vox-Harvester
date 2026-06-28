# --- local_coder/hallucination_guard.py ---
import re
import sys
from dataclasses import dataclass


@dataclass
class BannedPattern:
    name: str
    regex: re.Pattern
    description: str


@dataclass
class ScanResult:
    violations: list[tuple[int, str, BannedPattern]]
    total_count: int
    should_abort: bool


DEFAULT_BANNED_PATTERNS: list[BannedPattern] = [
    BannedPattern("import_statement", re.compile(r"^import\s+"), "Import statement"),
    BannedPattern("from_import", re.compile(r"^from\s+\S+\s+import"), "From-import statement"),
]


def _extract_symbols_from_file(file_path: str) -> list[str]:
    """Extract function and class names from a Python file."""
    symbols = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, IOError):
        print(f"Warning: Could not read file {file_path}", file=sys.stderr)
        return symbols

    func_pattern = re.compile(r"^\s*def\s+(\w+)", re.MULTILINE)
    symbols.extend(func_pattern.findall(content))

    class_pattern = re.compile(r"^\s*class\s+(\w+)", re.MULTILINE)
    symbols.extend(class_pattern.findall(content))

    return symbols


def sanitize_task_for_prose(task: str, context_files: list[str]) -> str:
    """Strip project-specific symbols from task description for Pass 1.

    Extracts function/class names from context files and removes them
    from the task description, preserving general intent.
    """
    all_symbols: set[str] = set()
    for file_path in context_files:
        symbols = _extract_symbols_from_file(file_path)
        all_symbols.update(symbols)

    if not all_symbols:
        return task

    escaped_symbols = [re.escape(s) for s in sorted(all_symbols, key=len, reverse=True)]
    symbols_pattern = re.compile(r"\b(" + "|".join(escaped_symbols) + r")\b")

    sanitized = symbols_pattern.sub("", task)
    sanitized = re.sub(r"  +", " ", sanitized).strip()
    return sanitized


def scan_for_hallucinations(
    prose_output: str,
    context_files: list[str],
    banned_patterns: list[BannedPattern] | None = None,
) -> ScanResult:
    """Scan prose model output for banned patterns indicating hallucination.

    Uses DEFAULT_BANNED_PATTERNS if none provided. Adds dynamic patterns
    derived from context_files (function/class names).
    """
    if banned_patterns is None:
        patterns = DEFAULT_BANNED_PATTERNS[:]
    else:
        patterns = banned_patterns[:]

    # Add dynamic patterns from context files
    all_symbols: set[str] = set()
    for file_path in context_files:
        symbols = _extract_symbols_from_file(file_path)
        all_symbols.update(symbols)

    if all_symbols:
        escaped = [re.escape(s) for s in sorted(all_symbols, key=len, reverse=True)]
        dynamic_regex = re.compile(r"\b(" + "|".join(escaped) + r")\b")
        patterns.append(BannedPattern("project_symbol", dynamic_regex, "Project-specific symbol"))

    lines = prose_output.splitlines()
    violations: list[tuple[int, str, BannedPattern]] = []

    for i, line in enumerate(lines, 1):
        for pattern in patterns:
            if pattern.regex.search(line):
                violations.append((i, line, pattern))
                break  # Only report first matching pattern per line

    total_count = len(violations)
    should_abort = total_count > 3

    return ScanResult(violations=violations, total_count=total_count, should_abort=should_abort)


def remove_violations(prose_output: str, scan_result: ScanResult) -> str:
    """Remove offending lines from prose output, preserving non-offending content and order."""
    if not scan_result.violations:
        return prose_output

    violation_lines = {line_num for line_num, _, _ in scan_result.violations}
    lines = prose_output.splitlines()
    filtered = [line for i, line in enumerate(lines, 1) if i not in violation_lines]
    return "\n".join(filtered)
