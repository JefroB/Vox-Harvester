"""Smoke tests for routing enforcement and fallback logic.

Validates Requirements 2.2, 2.3, 2.4, 2.6:
- routing: "local" + context exceeds Context_Window → fall back to cloud
- routing: "local" + Ollama unreachable → fall back to cloud
- routing: "cloud" → always dispatch to cloud
- routing: "auto" / absent → preserve existing behavior
"""

from unittest.mock import patch

from orchestrator.routing import (
    CONTEXT_WINDOW,
    RoutingDecision,
    check_ollama_reachable,
    enforce_routing,
)


class TestEnforceRoutingCloud:
    """routing: "cloud" → always dispatch to cloud (Req 2.3)."""

    def test_cloud_routing_returns_cloud(self):
        result = enforce_routing("cloud", estimated_tokens=100, ollama_reachable=True)
        assert result.target == "cloud"
        assert result.override_reason is None

    def test_cloud_routing_ignores_token_count(self):
        result = enforce_routing("cloud", estimated_tokens=999999, ollama_reachable=False)
        assert result.target == "cloud"
        assert result.override_reason is None


class TestEnforceRoutingAuto:
    """routing: "auto" → preserve existing behavior (Req 2.4)."""

    def test_auto_routing_returns_auto(self):
        result = enforce_routing("auto", estimated_tokens=100, ollama_reachable=True)
        assert result.target == "auto"
        assert result.override_reason is None

    def test_auto_routing_ignores_conditions(self):
        result = enforce_routing("auto", estimated_tokens=999999, ollama_reachable=False)
        assert result.target == "auto"
        assert result.override_reason is None


class TestEnforceRoutingLocalSuccess:
    """routing: "local" with conditions met → stays local."""

    def test_local_within_window_and_reachable(self):
        result = enforce_routing("local", estimated_tokens=10000, ollama_reachable=True)
        assert result.target == "local"
        assert result.override_reason is None

    def test_local_at_exact_window_boundary(self):
        """Exactly at Context_Window should NOT trigger fallback (> not >=)."""
        result = enforce_routing("local", estimated_tokens=CONTEXT_WINDOW, ollama_reachable=True)
        assert result.target == "local"
        assert result.override_reason is None

    def test_local_zero_tokens(self):
        result = enforce_routing("local", estimated_tokens=0, ollama_reachable=True)
        assert result.target == "local"
        assert result.override_reason is None


class TestEnforceRoutingLocalFallbackTokens:
    """routing: "local" + context exceeds Context_Window → cloud (Req 2.2)."""

    def test_exceeds_context_window(self):
        result = enforce_routing(
            "local", estimated_tokens=CONTEXT_WINDOW + 1, ollama_reachable=True
        )
        assert result.target == "cloud"
        assert result.override_reason is not None
        assert "Context_Window" in result.override_reason
        assert str(CONTEXT_WINDOW) in result.override_reason

    def test_far_exceeds_context_window(self):
        result = enforce_routing("local", estimated_tokens=100000, ollama_reachable=True)
        assert result.target == "cloud"
        assert "context exceeds" in result.override_reason


class TestEnforceRoutingLocalFallbackUnreachable:
    """routing: "local" + Ollama unreachable → cloud (Req 2.6)."""

    def test_ollama_unreachable(self):
        result = enforce_routing("local", estimated_tokens=1000, ollama_reachable=False)
        assert result.target == "cloud"
        assert result.override_reason is not None
        assert "unreachable" in result.override_reason.lower()

    def test_token_check_takes_priority_over_reachability(self):
        """If both conditions fail, token check is evaluated first."""
        result = enforce_routing(
            "local", estimated_tokens=CONTEXT_WINDOW + 1, ollama_reachable=False
        )
        assert result.target == "cloud"
        # Token check fires first since it's checked before reachability
        assert "Context_Window" in result.override_reason


class TestRoutingDecisionDataclass:
    """RoutingDecision dataclass basic behavior."""

    def test_default_override_reason_is_none(self):
        decision = RoutingDecision(target="local")
        assert decision.target == "local"
        assert decision.override_reason is None

    def test_with_override_reason(self):
        decision = RoutingDecision(target="cloud", override_reason="test reason")
        assert decision.target == "cloud"
        assert decision.override_reason == "test reason"

    def test_equality(self):
        d1 = RoutingDecision(target="cloud", override_reason=None)
        d2 = RoutingDecision(target="cloud", override_reason=None)
        assert d1 == d2


class TestCheckOllamaReachable:
    """check_ollama_reachable() network behavior (mocked)."""

    def test_reachable_returns_true(self):
        with patch("orchestrator.routing.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = lambda s, *a: None
            assert check_ollama_reachable(timeout=1.0) is True

    def test_connection_refused_returns_false(self):
        import urllib.error

        with patch("orchestrator.routing.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            assert check_ollama_reachable(timeout=1.0) is False

    def test_timeout_returns_false(self):
        with patch("orchestrator.routing.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("timed out")
            assert check_ollama_reachable(timeout=1.0) is False

    def test_os_error_returns_false(self):
        with patch("orchestrator.routing.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = OSError("Network unreachable")
            assert check_ollama_reachable(timeout=1.0) is False

    def test_default_timeout_is_10(self):
        """Verify the default timeout parameter is 10 seconds."""
        import inspect

        sig = inspect.signature(check_ollama_reachable)
        assert sig.parameters["timeout"].default == 10.0
