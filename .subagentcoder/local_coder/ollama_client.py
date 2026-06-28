"""Ollama client stub for local coder pipeline.

Provides the call_ollama() interface and OllamaError exception.
This module will be fully implemented when the Ollama integration task is executed.
"""

from __future__ import annotations


class OllamaError(Exception):
    """Raised when an Ollama API call fails."""

    pass


def call_ollama(
    prompt: str,
    model: str,
    context_files: list[str] | None = None,
    temperature: float = 0.2,
    ctx_size: int = 32768,
) -> dict:
    """Call the Ollama API with the given prompt and model.

    Args:
        prompt: The prompt text to send to the model.
        model: The Ollama model name (e.g., "qwen2.5-coder:7b").
        context_files: Optional list of file paths to include as context.
        temperature: Sampling temperature (default 0.2).
        ctx_size: Context window size in tokens.

    Returns:
        Dict with keys:
            - "response": str — the model's text response
            - "eval_count": int | None — token count from Ollama (may be missing/zero)
            - "total_duration": int — total duration in nanoseconds

    Raises:
        OllamaError: If the API call fails.
    """
    raise NotImplementedError(
        "ollama_client.call_ollama() is a stub. "
        "Wire up the actual Ollama HTTP client to use this."
    )
