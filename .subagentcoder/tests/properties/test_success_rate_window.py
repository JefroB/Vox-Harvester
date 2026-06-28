# Feature: local-coder-workflow-improvements, Property 11: Success Rate Sliding Window Calculation
"""Property test: The success rate calculation uses only the most recent
min(N, 20) records for the given tier, where N is the total count of records
with that tier.

**Validates: Requirements 5.2**
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.issue_logger import IssueLogger, IssueRecord


# Strategy for generating safe text (no newlines)
_safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\n\r",
    ),
    min_size=1,
    max_size=50,
).map(lambda s: s.replace("**", ""))


# Strategy for generating a valid IssueRecord with a specific tier
def _record_strategy(tier: st.SearchStrategy[str] = st.just("simple")) -> st.SearchStrategy[IssueRecord]:
    return st.builds(
        IssueRecord,
        date=st.from_regex(
            r"20[2-3][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]",
            fullmatch=True,
        ),
        task_description=_safe_text,
        model_used=_safe_text,
        result=st.sampled_from(["success", "fail"]),
        tokens_generated=st.one_of(st.none(), st.integers(min_value=0, max_value=100000)),
        generation_speed=st.one_of(
            st.none(),
            st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False),
        ),
        quality_notes=_safe_text,
        issues_found=st.just([]),
        complexity_tier=tier,
        review_iterations=st.integers(min_value=0, max_value=5),
    )


@settings(max_examples=100)
@given(
    records=st.lists(
        _record_strategy(st.sampled_from(["simple", "complex", "prose"])),
        min_size=1,
        max_size=30,
    ),
    tier=st.sampled_from(["simple", "complex", "prose"]),
)
def test_success_rate_uses_most_recent_min_n_20_records(
    records: list[IssueRecord], tier: str
) -> None:
    """Verify _calculate_tier_rate uses only the most recent min(N, 20) records for the tier."""
    logger = IssueLogger(Path("tmp_unused"))

    # Call the method under test
    successes, total, percentage = logger._calculate_tier_rate(records, tier)

    # Manually calculate expected values
    tier_records = [r for r in records if r.complexity_tier == tier]
    n = len(tier_records)
    expected_window = tier_records[-min(n, 20):] if n > 0 else []

    expected_total = len(expected_window)
    expected_successes = sum(1 for r in expected_window if r.result == "success")
    expected_percentage = (expected_successes / expected_total * 100) if expected_total > 0 else 0.0

    assert total == expected_total, (
        f"Total mismatch: got {total}, expected {expected_total} "
        f"(tier={tier}, N={n}, window=min({n}, 20)={min(n, 20)})"
    )
    assert successes == expected_successes, (
        f"Successes mismatch: got {successes}, expected {expected_successes} "
        f"(tier={tier}, total={total})"
    )
    assert abs(percentage - expected_percentage) < 1e-9, (
        f"Percentage mismatch: got {percentage}, expected {expected_percentage}"
    )


@settings(max_examples=100)
@given(
    records=st.lists(
        _record_strategy(st.just("complex")),
        min_size=21,
        max_size=30,
    ),
)
def test_window_ignores_records_beyond_20(records: list[IssueRecord]) -> None:
    """When more than 20 records exist for a tier, only the last 20 are used."""
    logger = IssueLogger(Path("tmp_unused"))

    successes, total, percentage = logger._calculate_tier_rate(records, "complex")

    # With >20 records all of same tier, window must be exactly 20
    assert total == 20, f"Expected window of 20, got {total} (had {len(records)} records)"

    # Verify it uses the LAST 20 records
    last_20 = records[-20:]
    expected_successes = sum(1 for r in last_20 if r.result == "success")
    assert successes == expected_successes, (
        f"Successes from last 20 mismatch: got {successes}, expected {expected_successes}"
    )


@settings(max_examples=100)
@given(
    records=st.lists(
        _record_strategy(st.just("prose")),
        min_size=1,
        max_size=19,
    ),
)
def test_window_uses_all_records_when_fewer_than_20(records: list[IssueRecord]) -> None:
    """When fewer than 20 records exist for a tier, all records are used."""
    logger = IssueLogger(Path("tmp_unused"))

    successes, total, percentage = logger._calculate_tier_rate(records, "prose")

    # All records are the same tier, so total should equal len(records)
    assert total == len(records), (
        f"Expected total={len(records)}, got {total}"
    )

    expected_successes = sum(1 for r in records if r.result == "success")
    assert successes == expected_successes
