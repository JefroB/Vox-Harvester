# Feature: subagent-improvements, Property 4: Routing Auto-Assignment Heuristics
"""Property-based tests for routing auto-assignment heuristics.

**Validates: Requirements 2.5**

For any task description, the auto-assignment function shall produce routing
"local" when description length ≤200 characters AND the description matches
boilerplate/extraction/repetitive/single-file patterns; "cloud" when the
description references multi-step reasoning, 2+ file interaction, SDK APIs,
or property-based tests; and "auto" otherwise.
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from orchestrator.routing import auto_assign_routing


# --- Keyword sets (mirroring the implementation's known keywords) ---

LOCAL_KEYWORDS = (
    "extract",
    "boilerplate",
    "repetitive",
    "single-file",
    "single file",
    "scaffold",
    "template",
    "data",
    "config",
    "simple",
)

CLOUD_KEYWORDS = (
    "multi-step",
    "multi step",
    "property-based test",
    "property test",
    "pbt",
    "multiple files",
    "sdk",
    "api",
    "architecture",
    "auth",
    "security",
    "complex logic",
    "reasoning",
)

# All keywords combined for filtering in the "auto" strategy
ALL_KEYWORDS = LOCAL_KEYWORDS + CLOUD_KEYWORDS


# --- Strategies ---

# Generate short descriptions (≤200 chars) containing one local keyword
local_descriptions = st.builds(
    lambda prefix, keyword, suffix: (prefix + " " + keyword + " " + suffix).strip(),
    prefix=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=0,
        max_size=50,
    ),
    keyword=st.sampled_from(LOCAL_KEYWORDS),
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=0,
        max_size=50,
    ),
).filter(lambda d: len(d) <= 200)

# Generate descriptions containing one cloud keyword (any length)
cloud_descriptions = st.builds(
    lambda prefix, keyword, suffix: (prefix + " " + keyword + " " + suffix).strip(),
    prefix=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=0,
        max_size=80,
    ),
    keyword=st.sampled_from(CLOUD_KEYWORDS),
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=0,
        max_size=80,
    ),
)

# Generate descriptions that don't contain any keywords (for "auto" routing)
# Use alphanumeric characters unlikely to accidentally form keywords
auto_descriptions = st.text(
    alphabet=st.characters(whitelist_categories=("Lu",)),
    min_size=1,
    max_size=300,
).filter(
    lambda d: not any(kw.lower() in d.lower() for kw in ALL_KEYWORDS)
)


# --- Property Tests ---


@settings(max_examples=100)
@given(description=local_descriptions)
def test_local_routing_for_short_descriptions_with_local_keywords(description):
    """Descriptions ≤200 chars with local keywords route to 'local',
    unless they also contain a cloud keyword (cloud takes precedence)."""
    result = auto_assign_routing(description)
    # Cloud keywords take precedence per the implementation contract
    has_cloud_keyword = any(kw.lower() in description.lower() for kw in CLOUD_KEYWORDS)
    if has_cloud_keyword:
        assert result == "cloud"
    else:
        assert result == "local"


@settings(max_examples=100)
@given(description=cloud_descriptions)
def test_cloud_routing_for_descriptions_with_cloud_keywords(description):
    """Descriptions containing cloud keywords always route to 'cloud'."""
    result = auto_assign_routing(description)
    assert result == "cloud"


@settings(max_examples=100)
@given(description=auto_descriptions)
def test_auto_routing_for_descriptions_without_keywords(description):
    """Descriptions matching neither local nor cloud patterns route to 'auto'."""
    result = auto_assign_routing(description)
    assert result == "auto"
