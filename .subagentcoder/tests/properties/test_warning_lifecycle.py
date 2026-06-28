# Feature: local-coder-workflow-improvements, Property 12: Threshold Warning Lifecycle
"""Property-based tests for the threshold warning lifecycle in IssueLogger.

Validates that:
- WARNING appears in summary when a tier's last 10 records have <70% success (Req 5.4)
- WARNING is absent when a tier's last 10 records have >=70% success (Req 5.6)
- "insufficient data" annotation appears when a tier has <10 records (Req 5.5)

**Validates: Requirements 5.4, 5.5, 5.6**
"""

import shutil
import tempfile
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from local_coder.issue_logger import IssueLogger, IssueRecord


# --- Strategies ---

# Safe text without newlines or ** sequences that break markdown parsing
_safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\n\r",
    ),
    min_size=1,
    max_size=50,
).map(lambda s: s.replace("**", ""))

_tier_strategy = st.sampled_from(["simple", "complex", "prose"])


def _make_record(result: str, tier: str) -> IssueRecord:
    """Create a minimal valid IssueRecord with controlled result and tier."""
    return IssueRecord(
        date="2025-01-15T10:00:00",
        task_description="test task",
        model_used="test-model",
        result=result,
        tokens_generated=100,
        generation_speed=50.0,
        quality_notes="test",
        issues_found=["test-issue"] if result == "fail" else [],
        complexity_tier=tier,
        review_iterations=0,
    )


# Strategy: number of successes in last 10 that is below threshold (<7)
_below_threshold_successes = st.integers(min_value=0, max_value=6)

# Strategy: number of successes in last 10 that meets threshold (>=7)
_above_threshold_successes = st.integers(min_value=7, max_value=10)

# Strategy: number of records fewer than 10 for insufficient data
_insufficient_count = st.integers(min_value=1, max_value=9)

# Strategy: extra prefix records (to test that only last 10 matter)
_prefix_count = st.integers(min_value=0, max_value=5)


@settings(max_examples=50)
@given(
    tier=_tier_strategy,
    successes=_below_threshold_successes,
    prefix_records=_prefix_count,
)
def test_warning_when_below_threshold(
    tier: str, successes: int, prefix_records: int
) -> None:
    """When a tier has 10+ records and <70% success in last 10, WARNING appears."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        logger = IssueLogger(temp_dir)

        # Build records: some prefix records + exactly 10 records for the tier
        # where `successes` of the last 10 are "success" (and rest are "fail")
        all_records: list[IssueRecord] = []

        # Optional prefix records for the same tier (these get pushed out of last-10)
        for _ in range(prefix_records):
            all_records.append(_make_record("success", tier))

        # The critical last 10 records for this tier
        for i in range(10):
            result = "success" if i < successes else "fail"
            all_records.append(_make_record(result, tier))

        # Compute summary directly (no file I/O needed for the property)
        summary = logger._update_summary(all_records)

        # The summary line for this tier should contain WARNING
        # Find the line for this tier
        tier_line = None
        for line in summary.split("\n"):
            if f"**{tier}:**" in line:
                tier_line = line
                break

        assert tier_line is not None, f"No summary line found for tier '{tier}'"
        assert "WARNING" in tier_line, (
            f"Expected WARNING for tier '{tier}' with {successes}/10 successes, "
            f"but got: {tier_line}"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=50)
@given(
    tier=_tier_strategy,
    successes=_above_threshold_successes,
    prefix_records=_prefix_count,
)
def test_no_warning_when_above_threshold(
    tier: str, successes: int, prefix_records: int
) -> None:
    """When a tier has 10+ records and >=70% success in last 10, no WARNING for that tier."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        logger = IssueLogger(temp_dir)

        # Build records: some prefix records + exactly 10 records for the tier
        all_records: list[IssueRecord] = []

        # Optional prefix records for the same tier
        for _ in range(prefix_records):
            all_records.append(_make_record("fail", tier))

        # The critical last 10 records for this tier
        for i in range(10):
            result = "success" if i < successes else "fail"
            all_records.append(_make_record(result, tier))

        # Compute summary directly
        summary = logger._update_summary(all_records)

        # Find the line for this tier - it should NOT contain WARNING
        tier_line = None
        for line in summary.split("\n"):
            if f"**{tier}:**" in line:
                tier_line = line
                break

        assert tier_line is not None, f"No summary line found for tier '{tier}'"
        assert "WARNING" not in tier_line, (
            f"Expected no WARNING for tier '{tier}' with {successes}/10 successes, "
            f"but got: {tier_line}"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=50)
@given(
    tier=_tier_strategy,
    count=_insufficient_count,
)
def test_insufficient_data_annotation(tier: str, count: int) -> None:
    """When a tier has fewer than 10 records, summary shows 'insufficient data'."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        logger = IssueLogger(temp_dir)

        # Build fewer than 10 records for the target tier
        all_records: list[IssueRecord] = []
        for i in range(count):
            result = "success" if i % 2 == 0 else "fail"
            all_records.append(_make_record(result, tier))

        # Compute summary directly
        summary = logger._update_summary(all_records)

        # Find the line for this tier - it should contain "insufficient data"
        tier_line = None
        for line in summary.split("\n"):
            if f"**{tier}:**" in line:
                tier_line = line
                break

        assert tier_line is not None, f"No summary line found for tier '{tier}'"
        assert "insufficient data" in tier_line, (
            f"Expected 'insufficient data' for tier '{tier}' with {count} records, "
            f"but got: {tier_line}"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
