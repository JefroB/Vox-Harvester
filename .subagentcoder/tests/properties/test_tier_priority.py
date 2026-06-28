# Feature: local-coder-workflow-improvements, Property 4: Complexity Tier Assignment with Priority
"""Property-based tests for complexity tier assignment priority.

**Validates: Requirements 2.3, 2.7**

The _determine_complexity method classifies tasks into tiers with priority:
complex > prose > simple. When a task matches multiple tiers, the highest-weight
tier wins.
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pathlib import Path

from local_coder.task_annotator import TaskAnnotator

# --- Keyword sets (from the implementation) ---

COMPLEX_KEYWORDS = [
    "architecture", "auth", "security", "database", "module", "middleware",
    "migration", "concurrent", "async", "cryptography", "validation",
]

PROSE_KEYWORDS = [
    "document", "readme", "explanation", "tutorial", "guide",
    "blog", "summary",
]

CODE_KEYWORDS = ["implement", "function", "class", "code"]


# --- Strategies ---

# Descriptions containing BOTH a complex keyword AND a prose keyword
complex_and_prose_descriptions = st.builds(
    lambda prefix, ck, pk, suffix: f"{prefix} {pk} the {ck} {suffix}".strip(),
    prefix=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=20,
    ),
    ck=st.sampled_from(COMPLEX_KEYWORDS),
    pk=st.sampled_from(PROSE_KEYWORDS),
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=0,
        max_size=20,
    ),
)

# Descriptions containing a prose keyword but NO complex keywords and NO code keywords
prose_only_descriptions = st.builds(
    lambda prefix, pk, suffix: f"{prefix} {pk} {suffix}".strip(),
    prefix=st.text(
        alphabet=st.characters(whitelist_categories=("Lu",)),
        min_size=1,
        max_size=30,
    ),
    pk=st.sampled_from(PROSE_KEYWORDS),
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("Lu",)),
        min_size=0,
        max_size=30,
    ),
).filter(
    lambda d: (
        not any(kw in d.lower() for kw in COMPLEX_KEYWORDS)
        and not any(kw in d.lower() for kw in CODE_KEYWORDS)
        and len(d) <= 200
    )
)

# Long descriptions (>200 chars) without any complexity or prose keywords
long_no_keyword_descriptions = st.text(
    alphabet=st.characters(whitelist_categories=("Lu",)),
    min_size=201,
    max_size=300,
).filter(
    lambda d: (
        not any(kw in d.lower() for kw in COMPLEX_KEYWORDS)
        and not any(kw in d.lower() for kw in PROSE_KEYWORDS)
    )
)


# --- Property Tests ---


@settings(max_examples=100)
@given(description=complex_and_prose_descriptions)
def test_complex_always_wins(description):
    """When a description contains both a complex keyword and a prose keyword,
    the complex tier takes priority over prose (complex > prose > simple)."""
    annotator = TaskAnnotator(Path("/tmp/dummy"))
    result = annotator._determine_complexity(description, target_count=1)
    assert result == "complex", (
        f"Expected 'complex' for description with both complex and prose keywords, "
        f"got '{result}' for: {description!r}"
    )


@settings(max_examples=100)
@given(description=prose_only_descriptions)
def test_prose_wins_over_simple(description):
    """When a description contains a prose keyword but no complex keywords
    and no code keywords, the prose tier wins over simple."""
    annotator = TaskAnnotator(Path("/tmp/dummy"))
    result = annotator._determine_complexity(description, target_count=1)
    assert result == "prose", (
        f"Expected 'prose' for description with only prose keywords, "
        f"got '{result}' for: {description!r}"
    )


@settings(max_examples=100)
@given(description=long_no_keyword_descriptions)
def test_long_descriptions_are_complex(description):
    """Descriptions longer than 200 characters are always classified as complex,
    regardless of keyword presence."""
    annotator = TaskAnnotator(Path("/tmp/dummy"))
    result = annotator._determine_complexity(description, target_count=1)
    assert result == "complex", (
        f"Expected 'complex' for description >200 chars, "
        f"got '{result}' for length {len(description)}"
    )
