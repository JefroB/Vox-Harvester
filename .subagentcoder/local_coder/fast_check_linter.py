"""Post-generation lint for fast-check anti-patterns.

Scans generated test files for known fast-check mistakes that the local
model (qwen3:30b) consistently produces. These are mechanical errors that
can be auto-detected and flagged for fix.

Usage:
    from local_coder.fast_check_linter import lint_fast_check

    issues = lint_fast_check(generated_code)
    if issues:
        # Re-prompt or auto-fix
        fix_instructions = format_fix_instructions(issues)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FastCheckIssue:
    """A detected fast-check anti-pattern."""

    rule: str
    severity: str  # "error" or "warning"
    line_number: int | None
    message: str
    fix_hint: str


# Patterns to detect — each is (regex, rule_name, severity, message, fix_hint)
_LINT_RULES: list[tuple[re.Pattern, str, str, str, str]] = [
    (
        re.compile(r"Math\.random\s*\("),
        "no-math-random",
        "error",
        "Math.random() inside fc.property breaks shrinking. Use fast-check arbitraries instead.",
        "Replace Math.random() with an appropriate fc.* arbitrary passed as a property argument.",
    ),
    (
        re.compile(r"fc\.float\s*\((?!.*noNaN)"),
        "float-no-nan",
        "warning",
        "fc.float() without noNaN can produce NaN values that propagate unexpectedly.",
        "Add { noNaN: true } to fc.float() options.",
    ),
    (
        re.compile(r"fc\.array\s*\(.*?\)\.filter\s*\("),
        "array-filter",
        "error",
        "Filtering an entire fc.array() result causes 'too many skips' errors. Filter individual elements instead.",
        "Move the .filter() inside fc.array(): fc.array(fc.integer().filter(predicate)) instead of fc.array(fc.integer()).filter(predicate).",
    ),
    (
        re.compile(r"Date\.now\s*\("),
        "no-date-now",
        "error",
        "Date.now() inside fc.property introduces non-determinism that breaks reproducibility.",
        "Use fc.date() or fc.integer() as a time arbitrary instead of Date.now().",
    ),
    (
        re.compile(r"fc\.double\s*\(\s*\{[^}]*min\s*:\s*([^,}]+)\s*,\s*max\s*:\s*([^,}]+)"),
        "double-boundary-check",
        "warning",
        "Check that fc.double min < max — the model sometimes swaps boundaries.",
        "Verify that the min value is strictly less than the max value.",
    ),
]


def lint_fast_check(code: str) -> list[FastCheckIssue]:
    """Scan generated code for fast-check anti-patterns.

    Only scans code that appears to use fast-check (imports fc or fast-check).
    Returns an empty list if the code doesn't appear to be a fast-check test.

    Args:
        code: The generated source code to scan.

    Returns:
        List of FastCheckIssue objects for detected anti-patterns.
    """
    # Quick check: does this code even use fast-check?
    if "fc." not in code and "fast-check" not in code and "fc/" not in code:
        return []

    issues: list[FastCheckIssue] = []
    lines = code.splitlines()

    for rule_pattern, rule_name, severity, message, fix_hint in _LINT_RULES:
        for line_idx, line in enumerate(lines, start=1):
            if rule_pattern.search(line):
                # Special handling for double-boundary-check: verify min > max
                if rule_name == "double-boundary-check":
                    match = rule_pattern.search(line)
                    if match:
                        try:
                            min_val = float(match.group(1).strip())
                            max_val = float(match.group(2).strip())
                            if min_val >= max_val:
                                issues.append(FastCheckIssue(
                                    rule=rule_name,
                                    severity="error",
                                    line_number=line_idx,
                                    message=f"fc.double has min ({min_val}) >= max ({max_val})",
                                    fix_hint="Swap min and max values so min < max.",
                                ))
                        except (ValueError, IndexError):
                            # Can't parse as floats — skip this particular match
                            pass
                    continue

                issues.append(FastCheckIssue(
                    rule=rule_name,
                    severity=severity,
                    line_number=line_idx,
                    message=message,
                    fix_hint=fix_hint,
                ))

    return issues


def format_fix_instructions(issues: list[FastCheckIssue]) -> str:
    """Format lint issues into a fix instruction string for re-prompting.

    Args:
        issues: List of detected issues from lint_fast_check.

    Returns:
        A formatted string suitable for including in a re-prompt to the model.
    """
    if not issues:
        return ""

    lines = ["Fix the following fast-check anti-patterns in the generated code:\n"]

    for i, issue in enumerate(issues, start=1):
        line_ref = f" (line {issue.line_number})" if issue.line_number else ""
        lines.append(f"{i}. [{issue.severity.upper()}]{line_ref} {issue.message}")
        lines.append(f"   Fix: {issue.fix_hint}")
        lines.append("")

    lines.append("IMPORTANT: Do NOT use Math.random() inside fc.property blocks. "
                 "All randomness must come from fast-check arbitraries.")

    return "\n".join(lines)


def has_critical_issues(issues: list[FastCheckIssue]) -> bool:
    """Check if any of the issues are severity 'error'.

    Args:
        issues: List of detected issues.

    Returns:
        True if there's at least one error-severity issue.
    """
    return any(issue.severity == "error" for issue in issues)
