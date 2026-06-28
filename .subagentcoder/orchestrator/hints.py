"""Hints validation and processing for orchestrator dispatch.

Validates structured hints from the dispatch payload against the expected schema,
ignoring unrecognized keys and type-mismatched values with warnings while processing
all valid entries. Also handles context file budget accumulation for prompt injection
and dispatch helpers that translate validated hints into local coder CLI arguments
and routing decisions.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from models.task_graph import (
    HintsPayload,
    MAX_CONTEXT_FILES,
    MAX_SCOPE_LENGTH,
    VALID_COMPLEXITY_VALUES,
)

# Schema defining valid hint keys and their expected types/constraints.
# Each entry maps a JSON key name to a tuple of:
#   (dataclass_field_name, validator_function)
# The validator returns the validated value or raises ValueError on mismatch.

_HINTS_SCHEMA: dict[str, tuple[str, Any]] = {
    "preferLocalCoder": ("prefer_local_coder", lambda v: _validate_bool(v, "preferLocalCoder")),
    "complexity": ("complexity", lambda v: _validate_complexity(v)),
    "contextFiles": ("context_files", lambda v: _validate_context_files(v)),
    "skipReview": ("skip_review", lambda v: _validate_bool(v, "skipReview")),
    "scope": ("scope", lambda v: _validate_scope(v)),
    "distill": ("distill", lambda v: _validate_distill(v)),
    "tokenBudget": ("token_budget", lambda v: _validate_token_budget(v)),
}


def _validate_bool(value: Any, key_name: str) -> bool:
    """Validate that a value is a boolean (not an int masquerading as bool)."""
    if not isinstance(value, bool):
        raise ValueError(
            f"expected boolean for '{key_name}', got {type(value).__name__}: {value!r}"
        )
    return value


def _validate_complexity(value: Any) -> str:
    """Validate complexity is one of the allowed enum values."""
    if not isinstance(value, str):
        raise ValueError(
            f"expected string for 'complexity', got {type(value).__name__}: {value!r}"
        )
    if value not in VALID_COMPLEXITY_VALUES:
        raise ValueError(
            f"'complexity' must be one of {VALID_COMPLEXITY_VALUES}, got {value!r}"
        )
    return value


def _validate_context_files(value: Any) -> list[str]:
    """Validate contextFiles is an array of strings with max 20 entries."""
    if not isinstance(value, list):
        raise ValueError(
            f"expected array for 'contextFiles', got {type(value).__name__}: {value!r}"
        )
    if len(value) > MAX_CONTEXT_FILES:
        raise ValueError(
            f"'contextFiles' must have at most {MAX_CONTEXT_FILES} entries, got {len(value)}"
        )
    # Validate each element is a string
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"'contextFiles[{i}]' must be a string, got {type(item).__name__}: {item!r}"
            )
    return value


def _validate_scope(value: Any) -> str:
    """Validate scope is a string within the max length."""
    if not isinstance(value, str):
        raise ValueError(
            f"expected string for 'scope', got {type(value).__name__}: {value!r}"
        )
    if len(value) > MAX_SCOPE_LENGTH:
        raise ValueError(
            f"'scope' must be at most {MAX_SCOPE_LENGTH} characters, got {len(value)}"
        )
    return value


def _validate_distill(value: Any) -> bool:
    """Validate that distill is a boolean."""
    if not isinstance(value, bool):
        raise ValueError(
            f"expected boolean for 'distill', got {type(value).__name__}: {value!r}"
        )
    return value


def _validate_token_budget(value: Any) -> int:
    """Validate tokenBudget is an integer (not a boolean masquerading as int)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"expected integer for 'tokenBudget', got {type(value).__name__}: {value!r}"
        )
    return value


def validate_and_process_hints(
    raw_hints: dict,
) -> tuple[HintsPayload | None, list[str]]:
    """Validate and process raw hints from a dispatch payload.

    Takes a raw dictionary (parsed from JSON dispatch payload), validates each
    known key against expected types, ignores unrecognized keys with a warning,
    ignores type-mismatched values with a warning, and returns a HintsPayload
    with all valid fields populated plus a list of warning messages.

    Args:
        raw_hints: Dictionary of hint key-value pairs from the dispatch payload.

    Returns:
        A tuple of (HintsPayload with valid fields, list of warning strings).
        If raw_hints is None or not a dict, returns (None, [warning]).
    """
    warnings: list[str] = []

    if raw_hints is None:
        return None, []

    if not isinstance(raw_hints, dict):
        warnings.append(
            f"[WARN] hints: expected object, got {type(raw_hints).__name__} — ignoring entire hints field"
        )
        return None, warnings

    validated_fields: dict[str, Any] = {}

    for key, value in raw_hints.items():
        if key not in _HINTS_SCHEMA:
            warnings.append(
                f"[WARN] hints: unrecognized key '{key}' — ignoring"
            )
            continue

        field_name, validator = _HINTS_SCHEMA[key]

        try:
            validated_value = validator(value)
            validated_fields[field_name] = validated_value
        except ValueError as e:
            warnings.append(
                f"[WARN] hints: invalid value for '{key}' — {e}; ignoring"
            )

    # Build HintsPayload with only validated fields (others remain None)
    payload = HintsPayload(**validated_fields)

    # Post-validation: clamp token_budget to [500, 16000] if out of range
    if payload.token_budget is not None:
        if payload.token_budget < 500 or payload.token_budget > 16000:
            original = payload.token_budget
            clamped = max(500, min(16000, payload.token_budget))
            payload.token_budget = clamped
            warnings.append(
                f"[WARN] hints: 'tokenBudget' value {original} is outside "
                f"[500, 16000], clamped to {clamped}"
            )

    # Post-validation: tokenBudget without distill: true is meaningless
    if payload.token_budget is not None and payload.distill is not True:
        warnings.append(
            "[WARN] hints: 'tokenBudget' requires 'distill: true' — ignoring tokenBudget"
        )
        payload.token_budget = None

    # Emit warnings to stderr for observability
    for warning in warnings:
        print(warning, file=sys.stderr)

    return payload, warnings


# 60% of Context_Window (32768 tokens)
CONTEXT_BUDGET_TOKENS = 19660


def accumulate_context_files(
    file_paths: list[str], project_root: Path
) -> tuple[list[str], list[str]]:
    """Accumulate context file contents within the token budget.

    Reads files sequentially in listed order, estimating tokens as len(content) // 4.
    Stops when the next file would exceed CONTEXT_BUDGET_TOKENS. Missing or unreadable
    files are skipped with a warning without stopping accumulation.

    Args:
        file_paths: Ordered list of file paths (relative to project_root or absolute).
        project_root: The project root directory for resolving relative paths.

    Returns:
        A tuple of (list of file contents that were included, list of warning messages).
        The included list is always a prefix of the original list (in order), excluding
        any skipped missing/unreadable files.
    """
    included: list[str] = []
    warnings: list[str] = []
    cumulative_tokens = 0

    for file_path in file_paths:
        resolved = project_root / file_path

        # Check if file exists and is readable
        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            warnings.append(
                f"[WARN] context-files: skipping '{file_path}' — {e}"
            )
            continue

        estimated_tokens = len(content) // 4

        if cumulative_tokens + estimated_tokens > CONTEXT_BUDGET_TOKENS:
            # Budget exceeded — skip this and all remaining files
            remaining_count = len(file_paths) - file_paths.index(file_path)
            warnings.append(
                f"[WARN] context-files: budget exceeded at '{file_path}' "
                f"({cumulative_tokens} + {estimated_tokens} > {CONTEXT_BUDGET_TOKENS} tokens), "
                f"skipping {remaining_count} remaining file(s)"
            )
            break

        included.append(content)
        cumulative_tokens += estimated_tokens

    return included, warnings


# 80% of Context_Window (32768 tokens). When preferLocalCoder is True and the
# estimated prompt exceeds this threshold, the task falls back to cloud execution.
LOCAL_CODER_THRESHOLD_TOKENS: int = 26214


def build_local_coder_args(
    hints: HintsPayload, estimated_prompt_tokens: int
) -> tuple[list[str], bool | None]:
    """Build CLI arguments for local_coder.py from validated hints.

    Translates relevant HintsPayload fields into command-line arguments for
    local_coder.py and determines routing based on the preferLocalCoder hint
    and prompt token estimate.

    Args:
        hints: Validated HintsPayload instance.
        estimated_prompt_tokens: Estimated total token count for the prompt
            (task description + context files + skill injections).

    Returns:
        A tuple of (cli_args, should_use_local):
        - cli_args: List of CLI argument strings to pass to local_coder.py.
          May include ["--complexity", value] and/or ["--scope", value].
        - should_use_local:
          - True if preferLocalCoder is True AND estimated_prompt_tokens
            <= LOCAL_CODER_THRESHOLD_TOKENS (route to local).
          - False if preferLocalCoder is True AND estimated_prompt_tokens
            > LOCAL_CODER_THRESHOLD_TOKENS (fall back to cloud).
          - None if preferLocalCoder is not set (let caller decide).
    """
    cli_args: list[str] = []

    # Pass complexity to --complexity flag
    if hints.complexity is not None:
        cli_args.extend(["--complexity", hints.complexity])

    # Pass scope to --scope flag
    if hints.scope is not None:
        cli_args.extend(["--scope", hints.scope])

    # Pass distill flag
    if hints.distill is True:
        cli_args.append("--distill")
        # Pass token-budget only when distill is True
        if hints.token_budget is not None:
            cli_args.extend(["--token-budget", str(hints.token_budget)])

    # Determine routing decision based on preferLocalCoder
    should_use_local: bool | None
    if hints.prefer_local_coder is True:
        if estimated_prompt_tokens <= LOCAL_CODER_THRESHOLD_TOKENS:
            should_use_local = True
        else:
            should_use_local = False
    else:
        # prefer_local_coder is None or False — caller decides
        should_use_local = None

    return cli_args, should_use_local


def should_skip_review(hints: HintsPayload | None) -> bool:
    """Determine whether the generate-review-fix loop should be skipped.

    Args:
        hints: Validated HintsPayload instance, or None if no hints provided.

    Returns:
        True if hints is not None and hints.skip_review is True.
        False otherwise (including when hints is None or skip_review is None/False).
    """
    if hints is None:
        return False
    return hints.skip_review is True
