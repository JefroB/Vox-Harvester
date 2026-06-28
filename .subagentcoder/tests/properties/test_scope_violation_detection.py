# Feature: subagent-improvements, Property 19: Scope Violation Detection in Non-Patch Mode
"""Property test: For any original file content and modified file content with a
declared scope, the diff-based detector shall identify all changed line ranges that
do not overlap with the scope definition, and shall not flag any changed line ranges
that do overlap with the scope.

**Validates: Requirements 7.6**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scope_enforcer import detect_out_of_scope_changes, ScopeEntry


# --- Strategies ---


@st.composite
def scope_and_modifications_in_scope(draw: st.DrawFn):
    """Generate original content, a scope (line_range), and modifications WITHIN that scope.

    Returns (original_text, new_text, scope_entries) where changes are only within scope.

    Strategy: Generate lines where each line is unique (prevents SequenceMatcher from
    misattributing changes). Then replace exactly one line within the scope with a
    different unique value, ensuring the diff detects the change at the correct position.
    """
    # Use unique lines to prevent SequenceMatcher from finding unexpected matches
    n = draw(st.integers(min_value=8, max_value=25))
    lines = [f"line_{i}_content_{draw(st.integers(min_value=1000, max_value=9999))}" for i in range(n)]

    # Pick a scope range (1-based, inclusive) — leave room on both sides
    scope_start = draw(st.integers(min_value=2, max_value=max(2, n - 2)))
    scope_end = draw(st.integers(min_value=scope_start, max_value=min(n - 1, scope_start + 4)))

    # Modify exactly one line within the scope range (0-based index)
    change_idx = draw(st.integers(min_value=scope_start - 1, max_value=scope_end - 1))

    new_lines = list(lines)
    # Generate a replacement that's clearly different and unique
    new_lines[change_idx] = f"CHANGED_{change_idx}_{draw(st.integers(min_value=10000, max_value=99999))}"

    original_text = "\n".join(lines) + "\n"
    new_text = "\n".join(new_lines) + "\n"

    scope_entries = [
        ScopeEntry(kind="line_range", value=f"{scope_start}-{scope_end}",
                   start_line=scope_start, end_line=scope_end)
    ]

    return original_text, new_text, scope_entries


@st.composite
def scope_and_modifications_out_of_scope(draw: st.DrawFn):
    """Generate original content, a scope (line_range), and modifications OUTSIDE that scope.

    Returns (original_text, new_text, scope_entries) where changes are only outside scope.

    Strategy: Use unique lines and modify a line clearly after the scope range ends.
    """
    n = draw(st.integers(min_value=10, max_value=25))
    lines = [f"line_{i}_content_{draw(st.integers(min_value=1000, max_value=9999))}" for i in range(n)]

    # Pick a scope range in the early-middle part of the file, leaving room after
    scope_start = draw(st.integers(min_value=2, max_value=max(2, n - 5)))
    scope_end = draw(st.integers(min_value=scope_start, max_value=min(n - 3, scope_start + 3)))

    # Modify a line clearly AFTER the scope range (0-based index = scope_end or later,
    # which corresponds to 1-based line number > scope_end)
    change_idx = draw(st.integers(min_value=scope_end, max_value=n - 1))
    # 0-based index `scope_end` corresponds to 1-based line `scope_end + 1` which is outside

    new_lines = list(lines)
    new_lines[change_idx] = f"OUTOFSCOPE_{change_idx}_{draw(st.integers(min_value=10000, max_value=99999))}"

    original_text = "\n".join(lines) + "\n"
    new_text = "\n".join(new_lines) + "\n"

    scope_entries = [
        ScopeEntry(kind="line_range", value=f"{scope_start}-{scope_end}",
                   start_line=scope_start, end_line=scope_end)
    ]

    return original_text, new_text, scope_entries


# --- Property Tests ---


@settings(max_examples=100)
@given(data=scope_and_modifications_in_scope())
def test_in_scope_changes_produce_no_warnings(data) -> None:
    """Changes that overlap with the scope definition shall NOT be flagged."""
    original_text, new_text, scope_entries = data

    warnings = detect_out_of_scope_changes(original_text, new_text, scope_entries)

    assert warnings == [], (
        f"Expected no warnings for in-scope changes, got: {warnings}"
    )


@settings(max_examples=100)
@given(data=scope_and_modifications_out_of_scope())
def test_out_of_scope_changes_produce_warnings(data) -> None:
    """Changes that do NOT overlap with the scope definition shall be flagged."""
    original_text, new_text, scope_entries = data

    warnings = detect_out_of_scope_changes(original_text, new_text, scope_entries)

    assert len(warnings) > 0, (
        "Expected at least one warning for out-of-scope changes, got none"
    )
    # Each warning should mention "outside declared scope"
    for warning in warnings:
        assert "outside declared scope" in warning


@settings(max_examples=100)
@given(new_content=st.text(min_size=1, max_size=200))
def test_empty_original_returns_no_warnings(new_content: str) -> None:
    """When original is empty string (new file case), no warnings shall be produced."""
    scope_entries = [
        ScopeEntry(kind="line_range", value="1-10", start_line=1, end_line=10)
    ]

    warnings = detect_out_of_scope_changes("", new_content, scope_entries)

    assert warnings == [], (
        f"Expected empty warnings for new file case, got: {warnings}"
    )
