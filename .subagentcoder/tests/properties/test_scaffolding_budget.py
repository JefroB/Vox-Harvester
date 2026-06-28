# Feature: scaffolding-library, Property 6: Budget Never Exceeded
"""Property-based tests for budget enforcement.

**Validates: Requirements 3.4, 3.6, 4.5**

For any set of templates and for any budget value in [1, 100000], the sum of
token_estimates for all templates returned by _apply_budget SHALL be less than
or equal to the budget. Furthermore, the first template not included (if any)
would cause the cumulative total to exceed the budget (greedy-break property).
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scaffolding_selector import TemplateInfo, _apply_budget


# --- Strategies ---

# Template name: short random string
name_strategy = st.text(
    alphabet="abcdefghijklmnop",
    min_size=1,
    max_size=10,
)

# Token estimate: realistic range
token_estimate_strategy = st.integers(min_value=1, max_value=5000)

# Budget: range specified by the property
budget_strategy = st.integers(min_value=1, max_value=100000)


def _template_strategy():
    """Generate a single TemplateInfo with a random token_estimate."""
    return st.tuples(name_strategy, token_estimate_strategy).map(
        lambda t: TemplateInfo(
            name=t[0],
            path=Path("/tmp/fake"),
            tags=["test"],
            category="test",
            complexity="any",
            description="test",
            priority=0,
            source="shared",
            token_estimate=t[1],
        )
    )


# --- Property Tests ---


@settings(max_examples=100)
@given(
    templates=st.lists(_template_strategy(), min_size=0, max_size=20),
    budget=budget_strategy,
)
def test_budget_never_exceeded(templates, budget):
    """Verify _apply_budget never returns templates exceeding the budget.

    Two assertions:
    1) Sum of token_estimates of returned templates <= budget.
    2) Greedy-break: if not all templates were included, the first excluded
       template would cause the cumulative total to exceed the budget.
    """
    result = _apply_budget(templates, budget)

    # Assertion 1: Budget not exceeded
    total_tokens = sum(t.token_estimate for t in result)
    assert total_tokens <= budget, (
        f"Budget exceeded: total={total_tokens}, budget={budget}, "
        f"selected={len(result)} of {len(templates)} templates"
    )

    # Assertion 2: Greedy-break property
    # If some templates were excluded, the next one would exceed budget
    if len(result) < len(templates):
        next_template = templates[len(result)]
        assert total_tokens + next_template.token_estimate > budget, (
            f"Greedy-break violated: could have included template at index "
            f"{len(result)} (token_estimate={next_template.token_estimate}) "
            f"with remaining budget={budget - total_tokens}"
        )
