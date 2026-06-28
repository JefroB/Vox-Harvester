"""Two-pass prose and code generation pipeline.

Pass 1: Prose model generates markdown with TODO placeholders (no context files).
Pass 2: Code model replaces TODO placeholders with working implementations (with context).

Implements Requirements 7.1–7.5, 9.4, 9.5.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .hallucination_guard import (
    remove_violations,
    sanitize_task_for_prose,
    scan_for_hallucinations,
)
from .garbage_detector import check_garbage
from .ollama_client import OllamaError, call_ollama

# --- Model constants ---
PROSE_MODEL = "qwen3:8b"
FAST_MODEL = "qwen2.5-coder:7b"
HEAVY_MODEL = "qwen3-coder:30b-a3b-q4_K_M"


@dataclass
class TwoPassResult:
    """Result of the two-pass generation pipeline."""

    final_output: str
    prose_output: str
    pass1_model: str
    pass2_model: str
    escalated: bool
    escalation_reason: str | None
    pass1_eval_count: int = 0
    pass2_eval_count: int = 0


# --- Prompt templates ---

PASS1_PROMPT_TEMPLATE = """\
Write the following document using markdown. For any code examples, \
write ONLY a fenced code block containing a single comment:
# TODO: <description of what this code should do>

Do NOT write actual code. Use generic placeholders like <your-module>, \
<your-function> instead of specific project references.

Task: {sanitized_task}"""

PASS2_PROMPT_TEMPLATE = """\
Below is a markdown document with TODO placeholders in code blocks.
Replace each # TODO comment with a working implementation based on \
the reference code provided.

Document:
{prose_output}

Fill in all TODO blocks with correct, working code."""


def _extract_eval_count(result: dict, response_text: str) -> int:
    """Extract eval_count from Ollama response dict with fallback estimation.

    If eval_count is missing or zero, estimates tokens as len(response_text) // 4
    and logs a warning to stderr.

    Args:
        result: The Ollama response dict (with 'response', 'eval_count', etc.)
        response_text: The text response (used for fallback estimation).

    Returns:
        The eval_count or estimated token count.
    """
    eval_count = result.get("eval_count")
    if eval_count is None or eval_count == 0:
        estimated = len(response_text) // 4
        print(f"[TOKEN] eval_count missing, using estimate: {estimated}", file=sys.stderr)
        eval_count = estimated
    return eval_count


def execute_two_pass(
    task: str,
    context_files: list[str],
    output_path: str | None = None,
    prose_model: str = PROSE_MODEL,
    code_model: str = FAST_MODEL,
    code_complexity: str = "simple",
) -> TwoPassResult:
    """Execute the two-pass prose+code generation pipeline.

    Pass 1: Prose model generates markdown structure with TODO placeholders.
    Pass 2: Code model fills in the TODOs with real implementations.

    Args:
        task: The task description for generation.
        context_files: List of file paths to provide as context in Pass 2.
        output_path: Optional output file path (informational).
        prose_model: Model to use for Pass 1 (default: PROSE_MODEL).
        code_model: Model to use for Pass 2 (default: FAST_MODEL).
        code_complexity: Complexity level — "complex" selects HEAVY_MODEL,
            otherwise uses the code_model parameter.

    Returns:
        TwoPassResult with final output and metadata.
    """
    # Select the actual code model based on complexity
    effective_code_model = HEAVY_MODEL if code_complexity == "complex" else code_model

    # --- Pass 1: Prose generation (no context files) ---
    sanitized_task = sanitize_task_for_prose(task, context_files)
    pass1_prompt = PASS1_PROMPT_TEMPLATE.format(sanitized_task=sanitized_task)

    pass1_eval_count = 0
    pass2_eval_count = 0

    try:
        pass1_result = call_ollama(
            prompt=pass1_prompt,
            model=prose_model,
            context_files=None,  # No context for prose pass
        )
    except OllamaError as e:
        # Pass 1 OllamaError → escalate immediately
        return TwoPassResult(
            final_output="",
            prose_output="",
            pass1_model=prose_model,
            pass2_model=effective_code_model,
            escalated=True,
            escalation_reason=f"Pass 1 OllamaError: {e}",
            pass1_eval_count=0,
            pass2_eval_count=0,
        )

    # Extract response text and token count from Pass 1
    prose_output = pass1_result.get("response", "") if isinstance(pass1_result, dict) else pass1_result
    if isinstance(pass1_result, dict):
        pass1_eval_count = _extract_eval_count(pass1_result, prose_output)
    else:
        # Legacy string return — estimate tokens
        estimated = len(prose_output) // 4
        print(f"[TOKEN] eval_count missing, using estimate: {estimated}", file=sys.stderr)
        pass1_eval_count = estimated

    # --- Hallucination scan on Pass 1 output ---
    scan_result = scan_for_hallucinations(prose_output, context_files)

    if scan_result.should_abort:
        # More than 3 violations → abort and escalate (Req 7.5, 9.5)
        print(
            f"[TWO-PASS] Aborting: {scan_result.total_count} banned pattern violations "
            f"in prose output — escalating to cloud",
            file=sys.stderr,
        )
        return TwoPassResult(
            final_output="",
            prose_output=prose_output,
            pass1_model=prose_model,
            pass2_model=effective_code_model,
            escalated=True,
            escalation_reason=(
                f"Hallucination guardrail: {scan_result.total_count} banned patterns detected"
            ),
            pass1_eval_count=pass1_eval_count,
            pass2_eval_count=0,
        )

    # Remove violations if ≤ 3 (Req 9.4)
    if scan_result.total_count > 0:
        prose_output = remove_violations(prose_output, scan_result)

    # --- Pass 2: Code generation (with context files) ---
    pass2_prompt = PASS2_PROMPT_TEMPLATE.format(prose_output=prose_output)

    try:
        pass2_result = call_ollama(
            prompt=pass2_prompt,
            model=effective_code_model,
            context_files=context_files,
        )
    except OllamaError:
        # Pass 2 OllamaError → retry once
        try:
            pass2_result = call_ollama(
                prompt=pass2_prompt,
                model=effective_code_model,
                context_files=context_files,
            )
        except OllamaError as e:
            # Second failure → escalate
            return TwoPassResult(
                final_output="",
                prose_output=prose_output,
                pass1_model=prose_model,
                pass2_model=effective_code_model,
                escalated=True,
                escalation_reason=f"Pass 2 OllamaError after retry: {e}",
                pass1_eval_count=pass1_eval_count,
                pass2_eval_count=0,
            )

    # Extract response text and token count from Pass 2 (from the successful call)
    final_output = pass2_result.get("response", "") if isinstance(pass2_result, dict) else pass2_result
    if isinstance(pass2_result, dict):
        pass2_eval_count = _extract_eval_count(pass2_result, final_output)
    else:
        # Legacy string return — estimate tokens
        estimated = len(final_output) // 4
        print(f"[TOKEN] eval_count missing, using estimate: {estimated}", file=sys.stderr)
        pass2_eval_count = estimated

    return TwoPassResult(
        final_output=final_output,
        prose_output=prose_output,
        pass1_model=prose_model,
        pass2_model=effective_code_model,
        escalated=False,
        escalation_reason=None,
        pass1_eval_count=pass1_eval_count,
        pass2_eval_count=pass2_eval_count,
    )
