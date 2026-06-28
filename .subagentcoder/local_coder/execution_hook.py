"""Execution hook for automatic issue logging after local coder runs.

Bridges the local coder execution lifecycle with the Issue_Logger,
parsing stdout for stats, determining results from exit state,
and persisting structured records.

Also provides delegation enforcement utilities:
- inject_delegation_prompt: Wraps task prompts with mandatory local-coder instructions
- audit_delegation_compliance: Checks subagent output for evidence of local_coder.py usage
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from local_coder.issue_logger import IssueLogger, IssueLogWriteError, IssueRecord
from local_coder.stats_parser import parse_exit_result, parse_stats_line

MAX_REVIEW_ITERATIONS = 5

# Regex to detect [local-coder: ...] annotation in task descriptions
_LOCAL_CODER_ANNOTATION_RE = re.compile(
    r"\[local-coder:\s*([^\]]+)\]", re.IGNORECASE
)

# Evidence patterns that indicate local_coder.py was actually called
_DELEGATION_EVIDENCE_PATTERNS = [
    re.compile(r"python\s+\.kiro/scripts/local_coder\.py", re.IGNORECASE),
    re.compile(r"\[INFO\]\s*Model:\s*qwen", re.IGNORECASE),
    re.compile(r"\[INFO\]\s*Generated\s+\d+\s+tokens", re.IGNORECASE),
    re.compile(r"tok/s\)", re.IGNORECASE),
    re.compile(r"local_coder\.py", re.IGNORECASE),
]

# The mandatory delegation prompt block injected into subagent dispatches
_MANDATORY_DELEGATION_BLOCK = """
## MANDATORY LOCAL CODER DELEGATION

This task MUST be implemented by calling `python .kiro/scripts/local_coder.py`.
You are FORBIDDEN from writing the implementation yourself.

### Required workflow:
1. Parse the `[local-coder: ...]` annotation flags from the task description
2. Run: `python .kiro/scripts/local_coder.py --task "<task description>" <parsed flags>`
3. Wait for the command to complete
4. Review the generated output for logic bugs, missing imports, anti-patterns
5. Fix small issues directly; re-run for structural issues
6. Verify the build passes

### VIOLATIONS (any of these = delegation failure):
- Using fs_write or str_replace to create the target file content yourself
- Writing more than 5 lines of the implementation without calling local_coder.py first
- Deciding the task is "too complex" for the local model and doing it cloud-side
- Reading existing code and generating the file based on your own understanding

### ONLY EXCEPTION:
If `local_coder.py` fails (Ollama unreachable, timeout, exit code != 0), you MAY
implement directly AS A FALLBACK. You MUST emit to stderr:
`[DELEGATION-SKIP] local_coder.py failed: <reason>`

If the task has `[cloud-only: ...]` instead, ignore this constraint and implement directly.
""".strip()


def after_execution(
    task_description: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    model_used: str,
    complexity_tier: str,
    review_iterations: int,
    issues_detected: list[str],
    timeout: bool = False,
    project_root: Path | None = None,
) -> IssueRecord | None:
    """Called after each local coder execution to log the outcome.

    Returns the logged IssueRecord on success, or None if logging failed
    (error is reported to stderr).
    """
    if project_root is None:
        project_root = Path.cwd()

    # Parse execution stats from stdout
    stats = parse_stats_line(stdout)

    # Determine result and exit-related issues
    result, exit_issues = parse_exit_result(exit_code, stderr, timeout)

    # Cap review iterations
    capped_iterations = min(review_iterations, MAX_REVIEW_ITERATIONS)
    if review_iterations > MAX_REVIEW_ITERATIONS:
        result = "fail"
        # Mark as abandoned
        if "abandoned" not in issues_detected:
            issues_detected = issues_detected + ["abandoned"]

    # Combine issues: detected + exit-related, cap at 10
    all_issues = (issues_detected + exit_issues)[:10]

    # Build quality notes
    if result == "success":
        if capped_iterations == 0:
            quality_notes = "Clean implementation, passed on first review"
        else:
            quality_notes = f"Passed after {capped_iterations} review iteration(s)"
    else:
        if review_iterations > MAX_REVIEW_ITERATIONS:
            quality_notes = f"Abandoned after {MAX_REVIEW_ITERATIONS} iterations"
        elif timeout:
            quality_notes = "Execution timed out"
        else:
            quality_notes = f"Failed with {len(all_issues)} issue(s) found"

    # Build the record
    record = IssueRecord(
        date=datetime.now().isoformat(timespec="seconds"),
        task_description=task_description,
        model_used=model_used,
        result=result,
        tokens_generated=stats.tokens_generated,
        generation_speed=stats.generation_speed,
        quality_notes=quality_notes,
        issues_found=all_issues,
        complexity_tier=complexity_tier,
        review_iterations=capped_iterations,
    )

    # Persist
    try:
        logger = IssueLogger(project_root)
        logger.log_execution(record)
        return record
    except IssueLogWriteError as e:
        print(f"ERROR: Failed to write issue log: {e.reason}", file=sys.stderr)
        return None


def has_local_coder_annotation(task_description: str) -> bool:
    """Check if a task description contains a [local-coder: ...] annotation.

    Args:
        task_description: The task description text to check.

    Returns:
        True if the annotation is present, False otherwise.
    """
    return bool(_LOCAL_CODER_ANNOTATION_RE.search(task_description))


def parse_local_coder_annotation(task_description: str) -> str | None:
    """Extract the flags string from a [local-coder: ...] annotation.

    Args:
        task_description: The task description text to parse.

    Returns:
        The flags string (e.g., "--tags code --complexity complex --output src/foo.py"),
        or None if no annotation is found.
    """
    match = _LOCAL_CODER_ANNOTATION_RE.search(task_description)
    if match:
        return match.group(1).strip()
    return None


def inject_delegation_prompt(task_description: str) -> str:
    """Wrap a task description with the mandatory delegation block.

    If the task contains a [local-coder: ...] annotation, prepends the
    mandatory delegation instructions to the task description. If no
    annotation is present, returns the description unchanged.

    This function is the programmatic equivalent of Option B — it ensures
    the enforcement text is always injected without relying on the
    orchestrator to remember.

    Args:
        task_description: The original task description.

    Returns:
        The task description with delegation instructions prepended,
        or the original description if no annotation is present.
    """
    if not has_local_coder_annotation(task_description):
        return task_description

    return f"{_MANDATORY_DELEGATION_BLOCK}\n\n---\n\n{task_description}"


def audit_delegation_compliance(
    task_description: str,
    subagent_output: str,
) -> tuple[bool, str | None]:
    """Check whether a subagent actually called local_coder.py for a delegated task.

    Searches the subagent's output (stdout + any execution logs) for evidence
    that local_coder.py was invoked. If no evidence is found, the task is
    flagged as a delegation bypass.

    This is the programmatic implementation of Option A — post-execution audit.

    Args:
        task_description: The original task description (to confirm it has
            a [local-coder: ...] annotation).
        subagent_output: The full text output from the subagent's execution,
            including shell command outputs and any logs.

    Returns:
        Tuple of (compliant, violation_reason):
        - (True, None) if delegation was honored or task has no annotation
        - (False, reason) if delegation was bypassed
    """
    # If no local-coder annotation, compliance is trivially satisfied
    if not has_local_coder_annotation(task_description):
        return (True, None)

    # Check for explicit delegation skip (legitimate fallback)
    if "[DELEGATION-SKIP]" in subagent_output:
        # Legitimate fallback — local_coder.py was attempted but failed
        return (True, None)

    # Check for evidence of local_coder.py execution
    for pattern in _DELEGATION_EVIDENCE_PATTERNS:
        if pattern.search(subagent_output):
            return (True, None)

    # No evidence found — delegation was bypassed
    return (
        False,
        "No evidence of local_coder.py execution found in subagent output. "
        "Task was likely implemented cloud-side in violation of [local-coder: ...] annotation.",
    )
