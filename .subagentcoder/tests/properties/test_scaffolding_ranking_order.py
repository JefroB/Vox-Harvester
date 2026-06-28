# Feature: scaffolding-library, Property 5: Ranking Order Invariant
"""Property-based tests for ranking order invariant.

**Validates: Requirements 3.3**

For any set of matched candidate templates (after tag/complexity filtering),
the list returned by _rank_candidates SHALL be sorted by the composite key:
(tag_overlap_count descending, priority descending, name ascending). For any
adjacent pair (a, b) in the result, either a has more tag overlap, or equal
overlap with higher priority, or equal overlap and priority with
lexicographically earlier or equal name.
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scaffolding_selector import TemplateInfo, _rank_candidates


# --- Strategies ---

# Pool of possible tags to draw from
_tag_pool = st.sampled_from(["alpha", "beta", "gamma", "delta", "epsilon"])

# Task tags: non-empty subset from the pool
task_tags_strategy = st.lists(_tag_pool, min_size=1, max_size=5, unique=True)

# Template name: short random string for deterministic sorting
name_strategy = st.text(
    alphabet="abcdefghijklmnop",
    min_size=1,
    max_size=10,
)

# Priority: integer range
priority_strategy = st.integers(min_value=-10, max_value=10)

# Template tags: drawn from the same pool, ensuring at least one overlap with task_tags
# We use a composite strategy that takes task_tags and builds template tags from them


def _template_tags_strategy(task_tags):
    """Generate template tags ensuring at least one overlaps with task_tags.

    Always include at least one tag from task_tags, then optionally add others.
    """
    # Pick at least one tag from task_tags to guarantee overlap
    overlap_tags = st.lists(
        st.sampled_from(task_tags), min_size=1, max_size=min(3, len(task_tags))
    )
    # Optionally add extra tags from the full pool
    extra_tags = st.lists(_tag_pool, min_size=0, max_size=3)
    return st.tuples(overlap_tags, extra_tags).map(
        lambda pair: list(set(pair[0] + pair[1]))
    )


def _candidate_strategy(task_tags):
    """Generate a single TemplateInfo candidate that overlaps with task_tags."""
    return st.tuples(
        name_strategy,
        _template_tags_strategy(task_tags),
        priority_strategy,
    ).map(
        lambda t: TemplateInfo(
            name=t[0],
            path=Path(f"/fake/{t[0]}.md"),
            tags=t[1],
            category="test-skeleton",
            complexity="any",
            description="test template",
            priority=t[2],
            source="shared",
            token_estimate=100,
        )
    )


# --- Property Tests ---


@settings(max_examples=100)
@given(data=st.data())
def test_ranking_order_invariant(data):
    """Verify _rank_candidates returns results sorted by composite key.

    For all adjacent pairs (a, b) in the result:
    - Either a has strictly more tag overlap with task_tags than b, OR
    - They have equal overlap and a.priority > b.priority, OR
    - They have equal overlap and equal priority and a.name <= b.name.
    """
    # Generate task tags first
    task_tags = data.draw(task_tags_strategy, label="task_tags")

    # Generate candidates that all have at least one overlapping tag
    candidates = data.draw(
        st.lists(
            _candidate_strategy(task_tags),
            min_size=2,
            max_size=15,
        ),
        label="candidates",
    )

    # Run the ranking function
    result = _rank_candidates(candidates, task_tags)

    # All candidates should pass the filter since they all have overlap
    assert len(result) > 0, "Expected non-empty result since all candidates overlap"

    # Check adjacent-pair ordering invariant
    task_tags_set = set(task_tags)
    for i in range(len(result) - 1):
        a, b = result[i], result[i + 1]
        overlap_a = len(set(a.tags) & task_tags_set)
        overlap_b = len(set(b.tags) & task_tags_set)

        assert (
            (overlap_a > overlap_b)
            or (overlap_a == overlap_b and a.priority > b.priority)
            or (overlap_a == overlap_b and a.priority == b.priority and a.name <= b.name)
        ), (
            f"Ranking order violated at index {i}:\n"
            f"  a: name={a.name!r}, overlap={overlap_a}, priority={a.priority}\n"
            f"  b: name={b.name!r}, overlap={overlap_b}, priority={b.priority}\n"
            f"  task_tags={task_tags}"
        )
