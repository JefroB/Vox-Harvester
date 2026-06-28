"""Parse execution statistics from local coder stdout."""

import re
from dataclasses import dataclass


@dataclass
class ExecutionStats:
    """Parsed statistics from a local coder execution."""

    model_name: str | None
    tokens_generated: int | None
    generation_speed: float | None


# Matches: <N> tokens in <T>s (<S> tok/s)
# N = non-negative integer, T = positive decimal/integer, S = positive decimal/integer
_STATS_PATTERN = re.compile(
    r"(\d+)\s+tokens?\s+in\s+(\d+(?:\.\d+)?)s\s+\((\d+(?:\.\d+)?)\s*tok/s\)"
)


def parse_stats_line(stdout: str) -> ExecutionStats:
    """Parse the statistics line from local coder output.

    Matches pattern: `<N> tokens in <T>s (<S> tok/s)`
    Returns fields as None if pattern not found or malformed.
    """
    match = _STATS_PATTERN.search(stdout)
    if match is None:
        return ExecutionStats(model_name=None, tokens_generated=None, generation_speed=None)

    try:
        tokens_generated = int(match.group(1))
        generation_speed = float(match.group(3))
    except (ValueError, OverflowError):
        return ExecutionStats(model_name=None, tokens_generated=None, generation_speed=None)

    return ExecutionStats(
        model_name=None,
        tokens_generated=tokens_generated,
        generation_speed=generation_speed,
    )


def parse_exit_result(exit_code: int, stderr: str, timeout: bool = False) -> tuple[str, list[str]]:
    """Determine result and issues from process exit state.

    Returns (result, issues_found) tuple.
    Truncates stderr to 200 characters.
    """
    if timeout:
        return ("fail", ["timeout"])

    if exit_code != 0:
        truncated_stderr = stderr[:200] if len(stderr) > 200 else stderr
        issues: list[str] = [f"exit_code:{exit_code}"]
        if truncated_stderr:
            issues.append(truncated_stderr)
        return ("fail", issues)

    return ("success", [])
