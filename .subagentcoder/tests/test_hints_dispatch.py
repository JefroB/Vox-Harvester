"""Smoke tests for hints dispatch functions: build_local_coder_args and should_skip_review."""

from models.task_graph import HintsPayload
from orchestrator.hints import (
    LOCAL_CODER_THRESHOLD_TOKENS,
    build_local_coder_args,
    should_skip_review,
)


# --- build_local_coder_args tests ---


class TestBuildLocalCoderArgs:
    """Tests for build_local_coder_args()."""

    def test_complexity_adds_flag(self):
        """complexity hint adds --complexity flag to CLI args."""
        hints = HintsPayload(complexity="simple")
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=1000)
        assert args == ["--complexity", "simple"]

    def test_scope_adds_flag(self):
        """scope hint adds --scope flag to CLI args."""
        hints = HintsPayload(scope="validate_email, lines 10-50")
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=1000)
        assert args == ["--scope", "validate_email, lines 10-50"]

    def test_complexity_and_scope_together(self):
        """Both complexity and scope produce both flags."""
        hints = HintsPayload(complexity="complex", scope="MyClass.process")
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=1000)
        assert "--complexity" in args
        assert "complex" in args
        assert "--scope" in args
        assert "MyClass.process" in args

    def test_prefer_local_under_threshold_routes_local(self):
        """preferLocalCoder=True with tokens under threshold → should_use_local=True."""
        hints = HintsPayload(prefer_local_coder=True)
        _, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=LOCAL_CODER_THRESHOLD_TOKENS
        )
        assert should_use_local is True

    def test_prefer_local_over_threshold_falls_back(self):
        """preferLocalCoder=True with tokens over threshold → should_use_local=False."""
        hints = HintsPayload(prefer_local_coder=True)
        _, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=LOCAL_CODER_THRESHOLD_TOKENS + 1
        )
        assert should_use_local is False

    def test_prefer_local_not_set_returns_none(self):
        """preferLocalCoder not set → should_use_local=None (caller decides)."""
        hints = HintsPayload()
        _, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=1000
        )
        assert should_use_local is None

    def test_prefer_local_false_returns_none(self):
        """preferLocalCoder=False → should_use_local=None (caller decides)."""
        hints = HintsPayload(prefer_local_coder=False)
        _, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=1000
        )
        assert should_use_local is None

    def test_no_hints_fields_set_empty_args(self):
        """Empty hints produce empty CLI args and None routing."""
        hints = HintsPayload()
        args, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=5000
        )
        assert args == []
        assert should_use_local is None

    def test_context_files_not_passed_as_cli_arg(self):
        """context_files are NOT passed as CLI args (handled separately)."""
        hints = HintsPayload(context_files=["src/models.py"])
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=1000)
        assert "--context" not in args
        assert "src/models.py" not in args

    def test_skip_review_not_passed_as_cli_arg(self):
        """skip_review is NOT passed as a CLI arg (handled by should_skip_review)."""
        hints = HintsPayload(skip_review=True)
        args, _ = build_local_coder_args(hints, estimated_prompt_tokens=1000)
        assert "--skip-review" not in args

    def test_threshold_boundary_exact(self):
        """At exactly the threshold, should_use_local is True (<=)."""
        hints = HintsPayload(prefer_local_coder=True)
        _, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=26214
        )
        assert should_use_local is True

    def test_threshold_boundary_one_over(self):
        """One token over threshold, should_use_local is False."""
        hints = HintsPayload(prefer_local_coder=True)
        _, should_use_local = build_local_coder_args(
            hints, estimated_prompt_tokens=26215
        )
        assert should_use_local is False


# --- should_skip_review tests ---


class TestShouldSkipReview:
    """Tests for should_skip_review()."""

    def test_skip_review_true(self):
        """skip_review=True → returns True."""
        hints = HintsPayload(skip_review=True)
        assert should_skip_review(hints) is True

    def test_skip_review_false(self):
        """skip_review=False → returns False."""
        hints = HintsPayload(skip_review=False)
        assert should_skip_review(hints) is False

    def test_skip_review_none(self):
        """skip_review not set (None) → returns False."""
        hints = HintsPayload()
        assert should_skip_review(hints) is False

    def test_hints_none(self):
        """hints=None → returns False."""
        assert should_skip_review(None) is False


# --- LOCAL_CODER_THRESHOLD_TOKENS constant ---


class TestThresholdConstant:
    """Tests for the threshold constant value."""

    def test_threshold_value(self):
        """Threshold is 80% of 32768."""
        assert LOCAL_CODER_THRESHOLD_TOKENS == 26214

    def test_threshold_is_integer(self):
        """Threshold is an integer."""
        assert isinstance(LOCAL_CODER_THRESHOLD_TOKENS, int)
