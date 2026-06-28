"""Two-pass routing detection for the local coder pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutingDecision:
    """Result of two-pass routing detection."""

    is_two_pass: bool
    matched_keywords: list[str]
    reason: str


# Keyword combinations that trigger two-pass routing.
# Each entry: (list of required keywords, human-readable description).
TWO_PASS_TRIGGERS: list[tuple[list[str], str]] = [
    (["strategy", "example"], "strategy + example/code snippet"),
    (["strategy", "code snippet"], "strategy + example/code snippet"),
    (["documentation", "implementation"], "documentation + implementation"),
    (["template", "guidance", "pattern"], "template + guidance + pattern"),
]

# Indicators that a task wants both prose and code content.
PROSE_CODE_INDICATORS: list[str] = [
    "example",
    "code snippet",
    "implementation",
    "code block",
    "sample code",
]


def detect_two_pass(task: str, output_path: str | None = None) -> RoutingDecision:
    """Detect if a task should use the two-pass pipeline.

    Checks keyword combinations and .md output with prose+code indicators.
    Returns RoutingDecision with match details.
    """
    if not task.strip():
        return RoutingDecision(
            is_two_pass=False, matched_keywords=[], reason="empty task description"
        )

    lowercased_task = task.lower()

    for keywords, description in TWO_PASS_TRIGGERS:
        if all(keyword in lowercased_task for keyword in keywords):
            return RoutingDecision(
                is_two_pass=True, matched_keywords=keywords, reason=description
            )

    if output_path is not None and output_path.endswith(".md"):
        for indicator in PROSE_CODE_INDICATORS:
            if indicator in lowercased_task:
                return RoutingDecision(
                    is_two_pass=True,
                    matched_keywords=[indicator, ".md output"],
                    reason="markdown output with prose+code content",
                )

    return RoutingDecision(
        is_two_pass=False, matched_keywords=[], reason="no two-pass triggers matched"
    )


def format_routing_log(decision: RoutingDecision) -> str:
    """Format the stderr routing log message."""
    return f"[ROUTE] Two-pass pipeline triggered: {', '.join(decision.matched_keywords)}"
