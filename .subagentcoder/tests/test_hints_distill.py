"""Unit tests for hints integration with skill distillation.

Tests that validate_and_process_hints correctly handles distill/tokenBudget fields
and that build_local_coder_args emits the right CLI flags.

Validates: Requirements 5.3, 5.4, 5.6
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.hints import validate_and_process_hints, build_local_coder_args
from models.task_graph import HintsPayload


# ---------------------------------------------------------------------------
# build_local_coder_args emits correct flags
# ---------------------------------------------------------------------------


class TestBuildLocalCoderArgsDistillFlags:
    """Test that build_local_coder_args produces correct --distill and --token-budget flags."""

    def test_distill_true_emits_distill_flag(self):
        """HintsPayload(distill=True) → '--distill' in args."""
        hints = HintsPayload(distill=True)
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=5000)
        assert "--distill" in args

    def test_distill_true_with_token_budget_emits_both(self):
        """HintsPayload(distill=True, token_budget=6000) → '--distill' and '--token-budget 6000'."""
        hints = HintsPayload(distill=True, token_budget=6000)
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=5000)
        assert "--distill" in args
        assert "--token-budget" in args
        budget_idx = args.index("--token-budget")
        assert args[budget_idx + 1] == "6000"

    def test_distill_false_no_distill_flag(self):
        """HintsPayload(distill=False) → no '--distill' in args."""
        hints = HintsPayload(distill=False)
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=5000)
        assert "--distill" not in args

    def test_no_distill_field_no_distill_flag(self):
        """HintsPayload() (no distill) → no '--distill' in args."""
        hints = HintsPayload()
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=5000)
        assert "--distill" not in args

    def test_distill_true_with_complexity_emits_both(self):
        """HintsPayload(distill=True, complexity='complex') → both flags present."""
        hints = HintsPayload(distill=True, complexity="complex")
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=5000)
        assert "--distill" in args
        assert "--complexity" in args
        complexity_idx = args.index("--complexity")
        assert args[complexity_idx + 1] == "complex"


# ---------------------------------------------------------------------------
# Type mismatch handling
# ---------------------------------------------------------------------------


class TestTypeMismatchHandling:
    """Test that validate_and_process_hints rejects non-boolean distill and non-integer tokenBudget."""

    def test_distill_string_yes_is_rejected(self):
        """distill: 'yes' → payload.distill is None, warning emitted."""
        payload, warnings = validate_and_process_hints({"distill": "yes"})
        assert payload.distill is None
        assert any("distill" in w and "invalid" in w.lower() for w in warnings)

    def test_distill_integer_is_rejected(self):
        """distill: 1 → payload.distill is None, warning emitted."""
        payload, warnings = validate_and_process_hints({"distill": 1})
        assert payload.distill is None
        assert any("distill" in w and "invalid" in w.lower() for w in warnings)

    def test_token_budget_string_is_rejected(self):
        """tokenBudget: '4000' → payload.token_budget is None, warning emitted."""
        payload, warnings = validate_and_process_hints({"tokenBudget": "4000"})
        assert payload.token_budget is None
        assert any("tokenBudget" in w and "invalid" in w.lower() for w in warnings)

    def test_token_budget_float_is_rejected(self):
        """tokenBudget: 4.5 → payload.token_budget is None, warning emitted."""
        payload, warnings = validate_and_process_hints({"tokenBudget": 4.5})
        assert payload.token_budget is None
        assert any("tokenBudget" in w and "invalid" in w.lower() for w in warnings)

    def test_token_budget_bool_is_rejected(self):
        """tokenBudget: True → payload.token_budget is None, warning emitted."""
        payload, warnings = validate_and_process_hints({"tokenBudget": True})
        assert payload.token_budget is None
        assert any("tokenBudget" in w and "invalid" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Clamping behavior
# ---------------------------------------------------------------------------


class TestClampingBehavior:
    """Test that tokenBudget values outside [500, 16000] are clamped."""

    def test_below_minimum_clamped_to_500(self):
        """tokenBudget: 100 with distill:true → clamped to 500, warning."""
        payload, warnings = validate_and_process_hints({"distill": True, "tokenBudget": 100})
        assert payload.token_budget == 500
        assert any("clamped" in w.lower() for w in warnings)

    def test_above_maximum_clamped_to_16000(self):
        """tokenBudget: 20000 with distill:true → clamped to 16000, warning."""
        payload, warnings = validate_and_process_hints({"distill": True, "tokenBudget": 20000})
        assert payload.token_budget == 16000
        assert any("clamped" in w.lower() for w in warnings)

    def test_within_range_no_clamping(self):
        """tokenBudget: 4000 with distill:true → 4000, no clamping warning."""
        payload, warnings = validate_and_process_hints({"distill": True, "tokenBudget": 4000})
        assert payload.token_budget == 4000
        assert not any("clamped" in w.lower() for w in warnings)

    def test_token_budget_without_distill_ignored(self):
        """tokenBudget: 4000 without distill → payload.token_budget is None, warning about requiring distill."""
        payload, warnings = validate_and_process_hints({"tokenBudget": 4000})
        assert payload.token_budget is None
        assert any("requires" in w.lower() and "distill" in w.lower() for w in warnings)
