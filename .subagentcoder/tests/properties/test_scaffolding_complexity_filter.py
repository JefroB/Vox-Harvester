# Feature: scaffolding-library, Property 4: Complexity Filter
"""Property-based tests for complexity filtering.

**Validates: Requirements 3.2**

For any task complexity value in {"simple", "complex"} and for any set of
templates with varying complexity fields, all templates returned by
_filter_by_complexity SHALL have complexity equal to the task complexity OR
equal to "any". No template with a non-matching specific complexity shall
appear in results. When task_complexity is "any", all input candidates are
returned (no filtering).
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scaffolding_selector import TemplateInfo, _filter_by_complexity


# --- Strategies ---

# Complexity values for templates
complexity_strategy = st.sampled_from(["simple", "complex", "any"])

# Task complexity values (the full set including "any")
task_complexity_strategy = st.sampled_from(["simple", "complex", "any"])

# Strategy for generating a TemplateInfo with a random complexity
template_info_strategy = st.builds(
    TemplateInfo,
    name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))).filter(lambda s: s.strip() != ""),
    path=st.just(Path("/fake/template.md")),
    tags=st.just(["test"]),
    category=st.just("test-skeleton"),
    complexity=complexity_strategy,
    description=st.just("A test template"),
    priority=st.just(0),
    source=st.sampled_from(["shared", "project"]),
    token_estimate=st.integers(min_value=10, max_value=1000),
)

# List of candidate templates
candidates_strategy = st.lists(template_info_strategy, min_size=0, max_size=20)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    candidates=candidates_strategy,
    task_complexity=task_complexity_strategy,
)
def test_complexity_filter_property(candidates, task_complexity):
    """All returned templates have complexity matching task_complexity or 'any'.

    When task_complexity is 'any', all candidates pass through unchanged.
    When task_complexity is 'simple' or 'complex', only templates with matching
    complexity or complexity == 'any' are returned.
    """
    result = _filter_by_complexity(candidates, task_complexity)

    if task_complexity == "any":
        # All candidates should pass through — no filtering
        assert result == candidates, (
            f"When task_complexity='any', expected all {len(candidates)} candidates "
            f"to pass through, but got {len(result)}"
        )
    else:
        # Every returned template must have matching complexity or "any"
        for template in result:
            assert template.complexity == task_complexity or template.complexity == "any", (
                f"Template '{template.name}' has complexity '{template.complexity}' "
                f"but task_complexity is '{task_complexity}'. "
                f"Only '{task_complexity}' or 'any' should pass the filter."
            )

        # Additionally: every candidate that SHOULD be included IS included
        expected = [
            t for t in candidates
            if t.complexity == task_complexity or t.complexity == "any"
        ]
        assert result == expected, (
            f"Filter result doesn't match expected. "
            f"Expected {len(expected)} templates, got {len(result)}. "
            f"task_complexity='{task_complexity}'"
        )
