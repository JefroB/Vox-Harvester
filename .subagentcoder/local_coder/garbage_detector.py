"""Garbage output detection for local coder pipeline.

Detects when local model output is too short (likely truncated/garbage)
and provides formatting utilities for diagnostic logging.
"""
from dataclasses import dataclass

GARBAGE_THRESHOLD = 50

@dataclass
class GarbageCheckResult:
    is_garbage: bool
    token_count: int
    attempt: int

def check_garbage(output: str, attempt: int = 1) -> GarbageCheckResult:
    token_count = len(output) // 4
    return GarbageCheckResult(is_garbage=token_count < GARBAGE_THRESHOLD, token_count=token_count, attempt=attempt)

def format_garbage_log(result: GarbageCheckResult) -> str:
    return f'[GARBAGE] {result.token_count} tokens (attempt {result.attempt})'

def format_escalation_warning(task_id: str) -> str:
    return f'[RETRY FAIL] Task {task_id} produced garbage on retry — escalating to cloud'