# Feature: subagent-improvements, Property 5: Token-Threshold Routing Decision
"""Property-based tests for token-threshold routing decisions.

**Validates: Requirements 2.2, 3.3**

For any task with `routing: "local"` or `hints.preferLocalCoder: true`, the system
shall route to local execution when estimated total tokens is below the applicable
threshold (100% of Context_Window for routing:local, 80% for preferLocalCoder), and
shall fall back to cloud execution when above the threshold.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestrator.routing import enforce_routing, CONTEXT_WINDOW
from orchestrator.hints import build_local_coder_args, LOCAL_CODER_THRESHOLD_TOKENS
from models.task_graph import HintsPayload


# --- Strategies ---

# Token counts at or below CONTEXT_WINDOW (for routing: "local" under threshold)
tokens_under_context_window = st.integers(min_value=0, max_value=CONTEXT_WINDOW)

# Token counts above CONTEXT_WINDOW (for routing: "local" over threshold)
tokens_over_context_window = st.integers(min_value=CONTEXT_WINDOW + 1, max_value=100000)

# Token counts at or below LOCAL_CODER_THRESHOLD_TOKENS (80% of Context_Window)
tokens_under_local_coder_threshold = st.integers(
    min_value=0, max_value=LOCAL_CODER_THRESHOLD_TOKENS
)

# Token counts above LOCAL_CODER_THRESHOLD_TOKENS
tokens_over_local_coder_threshold = st.integers(
    min_value=LOCAL_CODER_THRESHOLD_TOKENS + 1, max_value=100000
)


# --- Property Tests ---


@settings(max_examples=100)
@given(estimated_tokens=tokens_under_context_window)
def test_routing_local_under_context_window_routes_to_local(estimated_tokens):
    """routing='local' with tokens <= CONTEXT_WINDOW routes to local
    (assuming Ollama is reachable)."""
    decision = enforce_routing(
        routing="local",
        estimated_tokens=estimated_tokens,
        ollama_reachable=True,
    )
    assert decision.target == "local"
    assert decision.override_reason is None


@settings(max_examples=100)
@given(estimated_tokens=tokens_over_context_window)
def test_routing_local_over_context_window_falls_back_to_cloud(estimated_tokens):
    """routing='local' with tokens > CONTEXT_WINDOW falls back to cloud."""
    decision = enforce_routing(
        routing="local",
        estimated_tokens=estimated_tokens,
        ollama_reachable=True,
    )
    assert decision.target == "cloud"
    assert decision.override_reason is not None


@settings(max_examples=100)
@given(estimated_tokens=tokens_under_local_coder_threshold)
def test_prefer_local_coder_under_threshold_routes_to_local(estimated_tokens):
    """preferLocalCoder=True with tokens <= LOCAL_CODER_THRESHOLD_TOKENS
    should_use_local = True."""
    hints = HintsPayload(prefer_local_coder=True)
    _cli_args, should_use_local = build_local_coder_args(hints, estimated_tokens)
    assert should_use_local is True


@settings(max_examples=100)
@given(estimated_tokens=tokens_over_local_coder_threshold)
def test_prefer_local_coder_over_threshold_falls_back_to_cloud(estimated_tokens):
    """preferLocalCoder=True with tokens > LOCAL_CODER_THRESHOLD_TOKENS
    should_use_local = False (fall back to cloud)."""
    hints = HintsPayload(prefer_local_coder=True)
    _cli_args, should_use_local = build_local_coder_args(hints, estimated_tokens)
    assert should_use_local is False
