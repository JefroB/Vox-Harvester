# Feature: subagent-improvements, Property 7: Context File Budget Accumulation
"""Property-based tests for context file budget accumulation.

**Validates: Requirements 3.5**

For any ordered list of context files with known token sizes, the system shall
include files sequentially until the cumulative token count would exceed 60% of
Context_Window (19,660 tokens), at which point all remaining files shall be
skipped, and the set of included files shall be a prefix of the original list.
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestrator.hints import accumulate_context_files, CONTEXT_BUDGET_TOKENS


# --- Helper ---


def create_temp_files_and_run(sizes: list[int]):
    """Create temp files with content of specified character lengths, run accumulate.

    Each file gets content of 'a' * size so that token estimate = size // 4.
    Returns (included, warnings, sizes) for assertion.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        paths = []
        for i, size in enumerate(sizes):
            filename = f"file_{i}.txt"
            file_path = tmp_path / filename
            file_path.write_text("a" * size, encoding="utf-8")
            paths.append(filename)

        included, warnings = accumulate_context_files(paths, tmp_path)
        return included, warnings


def compute_expected_prefix_length(sizes: list[int]) -> int:
    """Compute how many files should be included before budget is exceeded.

    Simulates the accumulation logic: include files until the next would
    push cumulative tokens over CONTEXT_BUDGET_TOKENS.
    """
    cumulative = 0
    for i, size in enumerate(sizes):
        tokens = size // 4
        if cumulative + tokens > CONTEXT_BUDGET_TOKENS:
            return i
        cumulative += tokens
    return len(sizes)


# --- Property Tests ---


@settings(max_examples=100)
@given(sizes=st.lists(st.integers(min_value=4, max_value=40000), min_size=1, max_size=15))
def test_included_files_form_prefix_of_original_list(sizes):
    """Included files are always a prefix of the original file list.

    The system processes files sequentially in order and stops at the first
    file that would exceed the budget. All files before that point are included.
    """
    included, warnings = create_temp_files_and_run(sizes)

    # The number of included files should not exceed the total
    assert len(included) <= len(sizes)

    # Verify that included files are indeed a prefix: their contents match
    # the expected files in order
    for i, content in enumerate(included):
        expected_content = "a" * sizes[i]
        assert content == expected_content, (
            f"Included file at index {i} has wrong content. "
            f"Expected length {sizes[i]}, got length {len(content)}"
        )


@settings(max_examples=100)
@given(sizes=st.lists(st.integers(min_value=4, max_value=40000), min_size=1, max_size=15))
def test_cumulative_tokens_never_exceed_budget(sizes):
    """The cumulative token count of included files never exceeds the budget.

    Token estimation is len(content) // 4. The sum of tokens for all included
    files must be at most CONTEXT_BUDGET_TOKENS.
    """
    included, warnings = create_temp_files_and_run(sizes)

    # Compute cumulative tokens of included files
    cumulative_tokens = sum(len(content) // 4 for content in included)

    assert cumulative_tokens <= CONTEXT_BUDGET_TOKENS, (
        f"Cumulative tokens {cumulative_tokens} exceeds budget {CONTEXT_BUDGET_TOKENS}"
    )


@settings(max_examples=100, deadline=None)
@given(sizes=st.lists(st.integers(min_value=4, max_value=40000), min_size=1, max_size=15))
def test_files_skipped_only_because_next_would_exceed_budget(sizes):
    """If files are skipped, it's because adding the next would exceed the budget.

    When the included set is shorter than the full list, the next file's tokens
    plus the cumulative would exceed CONTEXT_BUDGET_TOKENS.
    """
    included, warnings = create_temp_files_and_run(sizes)

    included_count = len(included)

    if included_count < len(sizes):
        # There are skipped files — verify the next file would bust the budget
        cumulative_tokens = sum(len(content) // 4 for content in included)
        next_file_tokens = sizes[included_count] // 4

        assert cumulative_tokens + next_file_tokens > CONTEXT_BUDGET_TOKENS, (
            f"Files were skipped but next file (tokens={next_file_tokens}) "
            f"plus cumulative ({cumulative_tokens}) = "
            f"{cumulative_tokens + next_file_tokens} does not exceed budget "
            f"{CONTEXT_BUDGET_TOKENS}"
        )


@settings(max_examples=100)
@given(sizes=st.lists(st.integers(min_value=4, max_value=40000), min_size=1, max_size=15))
def test_included_count_matches_expected_prefix(sizes):
    """The number of included files matches the expected prefix length.

    Independently computes how many files fit within the budget and verifies
    the function agrees.
    """
    included, warnings = create_temp_files_and_run(sizes)

    expected_count = compute_expected_prefix_length(sizes)

    assert len(included) == expected_count, (
        f"Expected {expected_count} files included, got {len(included)}. "
        f"Sizes: {sizes}"
    )
