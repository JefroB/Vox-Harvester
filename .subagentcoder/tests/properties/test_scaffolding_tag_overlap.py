# Feature: scaffolding-library, Property 3: Tag-Overlap Filter
"""Property-based tests for tag-overlap filtering in scaffolding selection.

**Validates: Requirements 3.1, 3.5, 7.4**

For any set of templates with various tag lists and for any non-empty task tag set,
all templates returned by _rank_candidates SHALL have at least one tag in common
with the task tags. Equivalently, no returned template has a tag set disjoint from
the task tags.
"""

from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.scaffolding_selector import _rank_candidates, TemplateInfo


# --- Strategies ---

# Generate tag strings: short alphanumeric words
tag_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=10,
)

# Generate a list of tags (non-empty, 1-5 tags per template)
tag_list_strategy = st.lists(tag_strategy, min_size=1, max_size=5)

# Generate task tags (non-empty, 1-5 tags)
task_tags_strategy = st.lists(tag_strategy, min_size=1, max_size=5)


@st.composite
def template_info_strategy(draw):
    """Generate a random TemplateInfo object with valid fields."""
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ))
    tags = draw(tag_list_strategy)
    priority = draw(st.integers(0, 10))

    return TemplateInfo(
        name=name,
        path=Path("/tmp/fake.md"),
        tags=tags,
        category="test",
        complexity="any",
        description="test template",
        priority=priority,
        source="shared",
        token_estimate=100,
    )


# Generate a list of candidate templates (1-20)
candidates_strategy = st.lists(template_info_strategy(), min_size=1, max_size=20)


# --- Property Tests ---


@settings(max_examples=100)
@given(candidates=candidates_strategy, task_tags=task_tags_strategy)
def test_all_returned_templates_have_tag_overlap(candidates, task_tags):
    """Every template returned by _rank_candidates has at least one tag in common with task_tags."""
    results = _rank_candidates(candidates, task_tags)
    task_tags_set = set(task_tags)

    for template in results:
        overlap = set(template.tags) & task_tags_set
        assert len(overlap) > 0, (
            f"Template '{template.name}' returned with tags {template.tags} "
            f"but has no overlap with task_tags {task_tags}"
        )


@settings(max_examples=100)
@given(candidates=candidates_strategy, task_tags=task_tags_strategy)
def test_no_disjoint_template_in_results(candidates, task_tags):
    """No template whose tags are completely disjoint from task_tags appears in results."""
    results = _rank_candidates(candidates, task_tags)
    task_tags_set = set(task_tags)
    result_names = {t.name for t in results}

    # Check that every candidate with disjoint tags is excluded
    for candidate in candidates:
        if set(candidate.tags) & task_tags_set:
            # Has overlap — may or may not be in results (could be filtered by other criteria)
            pass
        else:
            # Disjoint — must NOT be in results
            assert candidate not in results, (
                f"Template '{candidate.name}' with tags {candidate.tags} is disjoint "
                f"from task_tags {task_tags} but was returned in results"
            )


@settings(max_examples=100)
@given(candidates=candidates_strategy, task_tags=task_tags_strategy)
def test_all_overlapping_candidates_are_included(candidates, task_tags):
    """Every candidate that has at least one tag overlap with task_tags appears in results.

    This validates that _rank_candidates includes ALL matching templates (none dropped).
    """
    results = _rank_candidates(candidates, task_tags)
    task_tags_set = set(task_tags)

    # Collect all candidates that should be included (have tag overlap)
    expected_candidates = [
        c for c in candidates
        if set(c.tags) & task_tags_set
    ]

    assert len(results) == len(expected_candidates), (
        f"Expected {len(expected_candidates)} templates with tag overlap, "
        f"got {len(results)} in results.\n"
        f"Missing: {set(id(c) for c in expected_candidates) - set(id(r) for r in results)}"
    )
