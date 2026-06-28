"""Auto-assignment heuristics and routing enforcement for task dispatch.

Determines whether a task should be routed to local (Ollama), cloud, or left
as auto based on description keywords and length constraints.

Also provides routing enforcement logic that handles fallback scenarios:
- routing: "local" + context exceeds Context_Window → fall back to cloud
- routing: "local" + Ollama unreachable → fall back to cloud
- routing: "cloud" → always cloud
- routing: "auto" → preserve existing behavior

Requirement 2.5: Auto-assignment heuristics (orchestrator-side):
- "local": description ≤200 chars AND matches (data extraction | boilerplate |
  repetitive | single-file).
- "cloud": multi-step reasoning | 2+ file interaction | SDK APIs | property-based tests.
- "auto": neither category matches.

Requirements 2.2, 2.3, 2.4, 2.6: Routing enforcement and fallback logic.
"""

from __future__ import annotations

import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Literal

# Context window capacity for local models (tokens)
CONTEXT_WINDOW = 32768


@dataclass
class RoutingDecision:
    """Result of routing enforcement evaluation.

    Attributes:
        target: Where the task should be dispatched — "local", "cloud", or "auto".
        override_reason: If routing was overridden (e.g., fallback from local to cloud),
            a human-readable explanation of why. None if no override occurred.
    """

    target: Literal["local", "cloud", "auto"]
    override_reason: str | None = None


# Maximum description length for local routing eligibility
_LOCAL_MAX_LENGTH = 200

# Keywords / patterns indicating a task is suitable for local execution.
# Matched case-insensitively against the task description.
_LOCAL_KEYWORDS: tuple[str, ...] = (
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

# Keywords / patterns indicating a task requires cloud execution.
# Matched case-insensitively against the task description.
_CLOUD_KEYWORDS: tuple[str, ...] = (
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

# Pre-compiled case-insensitive patterns for efficient matching.
# Uses word-boundary-aware matching for short keywords to avoid false positives
# (e.g., "api" shouldn't match inside "capital").
_LOCAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b" + re.escape(kw) + r"\b") if len(kw) <= 4
    else re.compile(r"(?i)" + re.escape(kw))
    for kw in _LOCAL_KEYWORDS
]

_CLOUD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b" + re.escape(kw) + r"\b") if len(kw) <= 4
    else re.compile(r"(?i)" + re.escape(kw))
    for kw in _CLOUD_KEYWORDS
]


def auto_assign_routing(description: str) -> Literal["local", "cloud", "auto"]:
    """Determine routing for a task based on its description.

    Applies heuristics from Requirement 2.5:
    1. Returns "local" if len(description) <= 200 AND description contains
       keywords indicating data extraction, boilerplate, repetitive, or
       single-file tasks.
    2. Returns "cloud" if description contains keywords indicating multi-step
       reasoning, multiple file interaction, SDK APIs, or property-based tests.
    3. Returns "auto" otherwise.

    Cloud keywords are checked first — if a description matches both local and
    cloud patterns, cloud takes precedence (more complex tasks should not be
    routed locally).

    Args:
        description: Human-readable task description.

    Returns:
        One of "local", "cloud", or "auto".
    """
    # Check cloud patterns first (takes precedence over local)
    if _matches_cloud(description):
        return "cloud"

    # Check local patterns (length + keyword match required)
    if len(description) <= _LOCAL_MAX_LENGTH and _matches_local(description):
        return "local"

    return "auto"


def _matches_local(description: str) -> bool:
    """Return True if description matches any local routing keyword."""
    return any(pattern.search(description) for pattern in _LOCAL_PATTERNS)


def _matches_cloud(description: str) -> bool:
    """Return True if description matches any cloud routing keyword."""
    return any(pattern.search(description) for pattern in _CLOUD_PATTERNS)


def enforce_routing(
    routing: str, estimated_tokens: int, ollama_reachable: bool
) -> RoutingDecision:
    """Enforce routing preference with fallback logic.

    Evaluates the routing preference against runtime conditions and determines
    the final dispatch target. Handles fallback from local to cloud when:
    - Context exceeds the local model's Context_Window capacity.
    - The Ollama server is unreachable.

    Args:
        routing: The routing preference — "local", "cloud", or "auto".
        estimated_tokens: Estimated total token count (prompt + context + response).
        ollama_reachable: Whether Ollama responded to a health check.

    Returns:
        A RoutingDecision indicating the final target and any override reason.
    """
    if routing == "cloud":
        return RoutingDecision(target="cloud", override_reason=None)

    if routing == "auto":
        return RoutingDecision(target="auto", override_reason=None)

    # routing == "local": apply fallback checks
    if estimated_tokens > CONTEXT_WINDOW:
        return RoutingDecision(
            target="cloud",
            override_reason=f"context exceeds Context_Window ({CONTEXT_WINDOW} tokens)",
        )

    if not ollama_reachable:
        return RoutingDecision(
            target="cloud",
            override_reason="Ollama unreachable (connection refused or timeout)",
        )

    return RoutingDecision(target="local", override_reason=None)


def check_ollama_reachable(timeout: float = 10.0) -> bool:
    """Check if the local Ollama server is reachable.

    Attempts a GET request to http://localhost:11434 (Ollama's default endpoint).
    Returns True if the server responds within the timeout, False otherwise.

    Args:
        timeout: Maximum seconds to wait for a response. Defaults to 10.0.

    Returns:
        True if Ollama responded, False if connection refused, timed out, or errored.
    """
    try:
        req = urllib.request.Request("http://localhost:11434", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, TimeoutError):
        return False
