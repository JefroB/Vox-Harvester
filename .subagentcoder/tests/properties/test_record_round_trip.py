# Feature: local-coder-workflow-improvements, Property 6: Issue Record Serialization Round-Trip
"""Property test: For any valid IssueRecord, serializing it with _serialize_record,
parsing it back with _parse_record, and re-serializing should produce byte-identical
output after whitespace normalization.

**Validates: Requirements 3.1, 6.4, 6.6**
"""

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.issue_logger import IssueLogger, IssueRecord


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces to single space and trim trailing whitespace per line."""
    lines = text.split("\n")
    normalized = []
    for line in lines:
        # Collapse multiple spaces into one
        line = re.sub(r" +", " ", line)
        # Trim trailing whitespace
        line = line.rstrip()
        normalized.append(line)
    return "\n".join(normalized)


# Strategy for generating safe text (no newlines, no ** sequence)
def _safe_text(min_size: int = 0, max_size: int = 200) -> st.SearchStrategy[str]:
    """Generate text without newlines or '**' sequences that would break markdown parsing."""
    return st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),  # no surrogates
            blacklist_characters="\n\r",
        ),
        min_size=min_size,
        max_size=max_size,
    ).map(lambda s: s.replace("**", "").replace("\r", ""))


# Strategy for issues_found items: letters, numbers, and dashes only
_issue_item_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)


# Strategy for generating valid IssueRecord instances
_issue_record_strategy = st.builds(
    IssueRecord,
    date=st.from_regex(
        r"20[2-3][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]",
        fullmatch=True,
    ),
    task_description=_safe_text(min_size=0, max_size=200),
    model_used=_safe_text(min_size=1, max_size=50),
    result=st.sampled_from(["success", "fail"]),
    tokens_generated=st.one_of(st.none(), st.integers(min_value=0, max_value=1_000_000)),
    generation_speed=st.one_of(
        st.none(),
        st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
    ),
    quality_notes=_safe_text(min_size=0, max_size=500),
    issues_found=st.lists(_issue_item_strategy, max_size=10),
    complexity_tier=st.sampled_from(["simple", "complex", "prose"]),
    review_iterations=st.integers(min_value=0, max_value=10),
)


@settings(max_examples=100)
@given(record=_issue_record_strategy)
def test_serialize_parse_reserialize_round_trip(record: IssueRecord) -> None:
    """Serialize → parse → re-serialize produces identical output after whitespace normalization."""
    logger = IssueLogger(Path("tmp_unused"))

    # First serialization
    serialized = logger._serialize_record(record)

    # Parse back to IssueRecord
    parsed_record = logger._parse_record(serialized)

    # Re-serialize
    re_serialized = logger._serialize_record(parsed_record)

    # Normalize whitespace in both
    normalized_first = _normalize_whitespace(serialized)
    normalized_second = _normalize_whitespace(re_serialized)

    assert normalized_first == normalized_second, (
        f"Round-trip failed!\n"
        f"Original serialized (normalized):\n{normalized_first}\n\n"
        f"Re-serialized (normalized):\n{normalized_second}"
    )
