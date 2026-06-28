# Feature: local-coder-reliability, Property 11: Violation Removal Preserves Non-Offending Content
"""Property tests for hallucination_guard module.

Property 11: Violation Removal Preserves Non-Offending Content (Requirements 9.4)
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.hallucination_guard import (
    scan_for_hallucinations,
    remove_violations,
)


# --- Strategies ---

# Clean lines: text that does NOT match any banned pattern.
# Banned patterns are: ^import\s+ and ^from\s+\S+\s+import
# Use only letters/digits/spaces, and filter out anything starting with "import " or "from".
_safe_alphabet = st.characters(whitelist_categories=("L", "Nd", "Zs"))
_clean_line_strategy = st.text(alphabet=_safe_alphabet, min_size=1, max_size=50).filter(
    lambda s: not s.startswith("import ") and not s.startswith("from ")
)

# Banned lines: actual import statements that WILL match the default patterns.
_banned_line_strategy = st.sampled_from([
    "import os",
    "import sys",
    "import re",
    "import pathlib",
    "from pathlib import Path",
    "from os import getcwd",
    "from sys import argv",
])


# Validates: Requirements 9.4
@settings(max_examples=100)
@given(
    clean_lines=st.lists(_clean_line_strategy, min_size=1, max_size=10),
    banned_lines=st.lists(_banned_line_strategy, min_size=1, max_size=3),
    positions=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=3),
)
def test_violation_removal_preserves_non_offending_content(
    clean_lines: list[str], banned_lines: list[str], positions: list[float]
) -> None:
    """Feature: local-coder-reliability, Property 11: Violation Removal Preserves Non-Offending Content"""

    # Build combined text by interleaving banned lines at generated positions
    combined = list(clean_lines)
    for i, banned_line in enumerate(banned_lines):
        pos_frac = positions[i % len(positions)]
        insert_idx = int(pos_frac * (len(combined) + 1))
        insert_idx = min(insert_idx, len(combined))
        combined.insert(insert_idx, banned_line)

    prose_output = "\n".join(combined)

    # Scan and remove
    scan_result = scan_for_hallucinations(prose_output, [])
    result = remove_violations(prose_output, scan_result)
    result_lines = result.splitlines()

    # a. All banned-pattern lines are ABSENT from the result
    for banned_line in banned_lines:
        assert banned_line not in result_lines, (
            f"Banned line '{banned_line}' still present in result"
        )

    # b. All clean lines are PRESENT in the result
    for clean_line in clean_lines:
        assert clean_line in result_lines, (
            f"Clean line '{clean_line}' missing from result"
        )

    # c. The relative ordering of clean lines is preserved
    clean_set = set(clean_lines)
    result_clean_lines = [line for line in result_lines if line in clean_set]
    # Walk through original clean_lines and verify order is preserved
    result_idx = 0
    for clean_line in clean_lines:
        # Find this clean_line in result_clean_lines starting from result_idx
        found = False
        for j in range(result_idx, len(result_clean_lines)):
            if result_clean_lines[j] == clean_line:
                result_idx = j + 1
                found = True
                break
        assert found, (
            f"Clean line '{clean_line}' not found in correct order in result"
        )


# --- Property 10: Hallucination Scan Detects All Banned Patterns ---

import re

from local_coder.hallucination_guard import DEFAULT_BANNED_PATTERNS


def _matches_any_banned_pattern(line: str) -> bool:
    """Check if a line matches any DEFAULT_BANNED_PATTERNS regex."""
    for pattern in DEFAULT_BANNED_PATTERNS:
        if pattern.regex.search(line):
            return True
    return False


# Strategy: safe lines that do NOT match any banned pattern
_safe_line_prop10 = st.from_regex(r"\A[a-zA-Z][a-zA-Z0-9 ]{0,40}\Z", fullmatch=True).filter(
    lambda l: not _matches_any_banned_pattern(l)
)

# Strategy: banned lines that DO match DEFAULT_BANNED_PATTERNS
_import_line_prop10 = st.from_regex(r"\Aimport [a-z][a-z0-9_]{0,20}\Z", fullmatch=True)
_from_import_line_prop10 = st.from_regex(
    r"\Afrom [a-z][a-z0-9_]{0,15} import [a-z][a-z0-9_]{0,15}\Z", fullmatch=True
)
_banned_line_prop10 = st.one_of(_import_line_prop10, _from_import_line_prop10)

# Each element is a tuple (line_text, is_banned)
_tagged_line_prop10 = st.one_of(
    _safe_line_prop10.map(lambda l: (l, False)),
    _banned_line_prop10.map(lambda l: (l, True)),
)


# Validates: Requirements 9.3
@settings(max_examples=100)
@given(tagged_lines=st.lists(_tagged_line_prop10, min_size=1, max_size=20))
def test_hallucination_scan_detects_all_banned_patterns(
    tagged_lines: list[tuple[str, bool]],
) -> None:
    """Feature: local-coder-reliability, Property 10: Hallucination Scan Detects All Banned Patterns"""
    lines = [text for text, _ in tagged_lines]
    prose_output = "\n".join(lines)

    # Track expected violation line numbers (1-indexed)
    expected_violation_lines = {
        i + 1 for i, (_, is_banned) in enumerate(tagged_lines) if is_banned
    }

    # Call scan using only DEFAULT_BANNED_PATTERNS (context_files=[] adds no dynamic patterns)
    result = scan_for_hallucinations(prose_output, context_files=[])

    # Collect reported violation line numbers
    reported_violation_lines = {line_num for line_num, _, _ in result.violations}

    # Every banned line must be detected (no false negatives)
    missing = expected_violation_lines - reported_violation_lines
    assert not missing, (
        f"Missed violations at lines {missing}. "
        f"Text at those lines: {[lines[ln - 1] for ln in missing]}"
    )

    # No safe line should be reported (no false positives)
    false_positives = reported_violation_lines - expected_violation_lines
    assert not false_positives, (
        f"False positives at lines {false_positives}. "
        f"Text at those lines: {[lines[ln - 1] for ln in false_positives]}"
    )

    # Verify each violation has the correct line text and matching pattern
    for line_num, line_text, matched_pattern in result.violations:
        assert line_text == lines[line_num - 1], (
            f"Violation at line {line_num}: expected text '{lines[line_num - 1]}', "
            f"got '{line_text}'"
        )
        assert matched_pattern.regex.search(line_text), (
            f"Pattern '{matched_pattern.name}' reported for line {line_num} "
            f"but doesn't actually match: '{line_text}'"
        )
