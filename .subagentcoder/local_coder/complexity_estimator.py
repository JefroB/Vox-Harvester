"""
Complexity Estimator — Fibonacci-based task complexity scoring.

Assigns a deterministic Fibonacci complexity score (1–21) to tasks based on:
- Task description length
- Complex keyword signals
- Number of context files
- Output file type

The score is informational only — it does NOT influence model routing.
"""

import os

# Fibonacci scores mapping index 0–6 to story-point-like values
FIBONACCI_SCORES = [1, 2, 3, 5, 8, 13, 21]

# Keywords indicating complex tasks — mirrors the list in local_coder.py
# Defined here directly to avoid importing from the script (which isn't a package).
COMPLEX_KEYWORDS = [
    "architecture", "design", "multiple files", "module", "refactor",
    "auth", "security", "database", "migration", "API", "system",
    "integration", "service", "middleware", "pipeline", "orchestrat",
    "complex", "multi-step", "full implementation", "entire", "complete module"
]

# File extensions that reduce complexity (config/test files are simpler tasks)
_REDUCING_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".lock",
}

_TEST_INDICATORS = {"test_", "_test", "test.", "spec_", "_spec", "spec."}


def _is_test_file(path: str) -> bool:
    """Check if a file path looks like a test file."""
    basename = os.path.basename(path).lower()
    return any(indicator in basename for indicator in _TEST_INDICATORS)


def _get_extension(path: str) -> str:
    """Get the lowercase file extension from a path."""
    _, ext = os.path.splitext(path)
    return ext.lower()


def _count_keyword_matches(task: str) -> int:
    """Count how many COMPLEX_KEYWORDS appear in the task description."""
    task_lower = task.lower()
    count = 0
    for keyword in COMPLEX_KEYWORDS:
        if keyword.lower() in task_lower:
            count += 1
    return count


def estimate_complexity(
    task: str,
    context_files: list[str],
    output_path: str | None = None,
) -> int:
    """Assign a Fibonacci complexity score to a task.

    Scoring inputs:
    - task description length (chars)
    - keyword signals (uses COMPLEX_KEYWORDS)
    - number of context files
    - output file type (extension)

    Returns: one of {1, 2, 3, 5, 8, 13, 21}

    Raises:
        TypeError: If task is not a string.
    """
    if not isinstance(task, str):
        raise TypeError(f"task must be a string, got {type(task).__name__}")

    # Empty task → minimal complexity
    if not task.strip():
        return FIBONACCI_SCORES[0]

    # --- Base tier from description length ---
    length = len(task)
    if length < 100:
        score = 0  # low
    elif length <= 300:
        score = 1  # mid
    else:
        score = 2  # high

    # --- Keyword matches: +1 tier per 2 keywords ---
    keyword_matches = _count_keyword_matches(task)
    score += keyword_matches // 2

    # --- Context file count: +1 tier per 2 files ---
    file_count = len(context_files) if context_files else 0
    score += file_count // 2

    # --- Output file type modifier ---
    if output_path is not None:
        ext = _get_extension(output_path)
        if ext in _REDUCING_EXTENSIONS:
            score -= 1
        elif _is_test_file(output_path):
            score -= 1
        # .py, .ts, etc. are neutral (no modifier)

    # --- Complexity floor: tasks with keywords AND multiple files are inherently complex ---
    # Per Requirement 1.3: tasks referencing multiple files with complex keyword signals
    # must score in the high range {8, 13, 21} (index 4+).
    # Applied last to ensure the semantic floor cannot be overridden by modifiers.
    if keyword_matches >= 1 and file_count >= 3:
        score = max(score, 4)

    # Clamp to valid index range [0, 6]
    clamped = max(0, min(6, score))

    return FIBONACCI_SCORES[clamped]
