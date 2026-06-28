# Feature: skill-distillation, Property 8: Budget clamping to valid range
"""Property-based tests for budget clamping behavior.

**Validates: Requirements 3.2, 5.6**

For any integer provided as a token budget to the Distiller, the effective budget
SHALL be clamped to [0, 16000]. For any integer provided via the Hints field or
CLI --token-budget, values outside [500, 16000] SHALL be rejected (CLI) or
clamped (Hints) with a warning.
"""

import sys
from pathlib import Path

# Make distiller and orchestrator importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import (
    assemble_prompt,
    estimate_tokens,
    DistillConfig,
    ScoredSection,
    Section,
    CodeBlock,
)
from orchestrator.hints import validate_and_process_hints


# --- Strategies ---

VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
]

word_strategy = st.sampled_from(VOCAB)


@st.composite
def scored_sections_with_rules(draw, min_sections=2, max_sections=6):
    """Generate scored sections that have extractable rules."""
    num_sections = draw(st.integers(min_value=min_sections, max_value=max_sections))
    sections = []

    for _ in range(num_sections):
        heading_words = draw(st.lists(word_strategy, min_size=2, max_size=4))
        heading = " ".join(heading_words)

        num_rules = draw(st.integers(min_value=3, max_value=10))
        rules = []
        for _ in range(num_rules):
            rule_words = draw(st.lists(word_strategy, min_size=5, max_size=12))
            rules.append(f"- {' '.join(rule_words)}")
        body = "\n".join(rules)

        section = Section(
            heading=heading,
            body=body,
            code_blocks=[],
            is_preamble=False,
        )

        raw_score = draw(st.floats(min_value=0.3, max_value=1.0))
        skill_name = draw(st.sampled_from([
            "Python Basics", "Security Rules", "API Patterns",
        ]))

        sections.append(ScoredSection(
            section=section,
            skill_name=skill_name,
            raw_score=raw_score,
            normalized_score=raw_score,
        ))

    return sections


# --- Property Tests ---


@settings(max_examples=100)
@given(
    budget=st.integers(min_value=-100000, max_value=-1),
    scored_sections=scored_sections_with_rules(),
)
def test_distiller_clamps_negative_budget_to_zero(budget, scored_sections):
    """For budget < 0, the Distiller SHALL clamp to 0 (empty output).

    When a negative budget is passed to assemble_prompt, the effective budget
    becomes 0, producing an empty string output.
    """
    config = DistillConfig(token_budget=budget, threshold=0.3)
    text, tokens_used = assemble_prompt(scored_sections, config, always_sections=[])

    assert text == "", (
        f"Expected empty output for negative budget {budget}, got {len(text)} chars"
    )
    assert tokens_used == 0, (
        f"Expected 0 tokens for negative budget {budget}, got {tokens_used}"
    )


@settings(max_examples=100)
@given(
    budget=st.integers(min_value=16001, max_value=1000000),
    scored_sections=scored_sections_with_rules(),
)
def test_distiller_clamps_budget_above_max_to_16000(budget, scored_sections):
    """For budget > 16000, the Distiller SHALL clamp to 16000.

    The output token count must not exceed 16000 regardless of how large
    the requested budget is.
    """
    config = DistillConfig(token_budget=budget, threshold=0.3)
    text, tokens_used = assemble_prompt(scored_sections, config, always_sections=[])

    actual_tokens = estimate_tokens(text)
    assert actual_tokens <= 16000, (
        f"Budget {budget} should be clamped to 16000, but output was {actual_tokens} tokens"
    )


@settings(max_examples=100)
@given(
    budget=st.integers(min_value=0, max_value=16000),
    scored_sections=scored_sections_with_rules(),
)
def test_distiller_valid_range_not_clamped(budget, scored_sections):
    """For budget in [0, 16000], the effective budget equals the requested budget.

    The output token count must not exceed the exact budget value.
    """
    config = DistillConfig(token_budget=budget, threshold=0.3)
    text, tokens_used = assemble_prompt(scored_sections, config, always_sections=[])

    actual_tokens = estimate_tokens(text)
    assert actual_tokens <= budget, (
        f"Budget {budget} (valid range) should be respected exactly. "
        f"Output was {actual_tokens} tokens"
    )


@settings(max_examples=100)
@given(budget=st.integers(min_value=-100000, max_value=499))
def test_hints_clamps_budget_below_500(budget):
    """For tokenBudget < 500 via Hints, the payload SHALL be clamped to 500 with a warning.

    Values below 500 passed through the hints field are clamped upward.
    """
    raw_hints = {"distill": True, "tokenBudget": budget}
    payload, warnings = validate_and_process_hints(raw_hints)

    assert payload is not None
    assert payload.token_budget == 500, (
        f"Expected token_budget clamped to 500 for input {budget}, got {payload.token_budget}"
    )
    # A warning should be emitted about clamping
    clamping_warnings = [w for w in warnings if "clamped" in w]
    assert len(clamping_warnings) >= 1, (
        f"Expected a clamping warning for budget {budget}, got warnings: {warnings}"
    )


@settings(max_examples=100)
@given(budget=st.integers(min_value=16001, max_value=1000000))
def test_hints_clamps_budget_above_16000(budget):
    """For tokenBudget > 16000 via Hints, the payload SHALL be clamped to 16000 with a warning."""
    raw_hints = {"distill": True, "tokenBudget": budget}
    payload, warnings = validate_and_process_hints(raw_hints)

    assert payload is not None
    assert payload.token_budget == 16000, (
        f"Expected token_budget clamped to 16000 for input {budget}, got {payload.token_budget}"
    )
    # A warning should be emitted about clamping
    clamping_warnings = [w for w in warnings if "clamped" in w]
    assert len(clamping_warnings) >= 1, (
        f"Expected a clamping warning for budget {budget}, got warnings: {warnings}"
    )


@settings(max_examples=100)
@given(budget=st.integers(min_value=500, max_value=16000))
def test_hints_valid_range_no_clamping(budget):
    """For tokenBudget in [500, 16000] via Hints, no clamping and no warning."""
    raw_hints = {"distill": True, "tokenBudget": budget}
    payload, warnings = validate_and_process_hints(raw_hints)

    assert payload is not None
    assert payload.token_budget == budget, (
        f"Expected token_budget unchanged at {budget}, got {payload.token_budget}"
    )
    # No clamping warning should be present
    clamping_warnings = [w for w in warnings if "clamped" in w]
    assert len(clamping_warnings) == 0, (
        f"No clamping warning expected for valid budget {budget}, got: {warnings}"
    )
