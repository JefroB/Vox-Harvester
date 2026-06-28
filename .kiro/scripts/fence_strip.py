"""
Fence Stripper — Strip outermost markdown code fences from model output.

This module provides `strip_markdown_fences()` which uses a state-machine parser
to correctly handle nested fences, extracting only outermost block contents.

Usage:
    from fence_strip import strip_markdown_fences, FenceStripError

    content, was_stripped = strip_markdown_fences(model_output)
"""

import re


class FenceStripError(ValueError):
    """Raised when fence stripping produces empty or whitespace-only output."""

    def __init__(self, message: str = "Stripping produced empty output"):
        super().__init__(message)
        self.message = message


# Pattern matching a fence line: optional leading whitespace, 3+ backticks,
# optional language tag (word characters, dots, hyphens, plus signs).
_FENCE_PATTERN = re.compile(r"^\s*(`{3,})([\w.+\-]*)?\s*$")


def _is_fence_line(line: str) -> tuple[bool, int]:
    """Check if a line is a markdown fence.

    Returns:
        (is_fence, backtick_count) — backtick_count is the number of
        consecutive backticks in the fence marker (used for matching
        open/close pairs with same or greater length).
    """
    match = _FENCE_PATTERN.match(line)
    if match:
        return True, len(match.group(1))
    return False, 0


def strip_markdown_fences(text: str) -> tuple[str, bool]:
    """Strip outermost markdown fences from model output.

    Uses a state-machine parser that tracks fence depth to correctly
    handle nested fences (only the outermost pairs are stripped).

    Returns:
        Tuple of (stripped_content, was_stripped).
        was_stripped is True if fences were found and removed.

    Rules:
        - Match outermost fence pairs only (nested fences are content).
        - Single block: extract content between fences.
        - Multiple blocks: join contents with single newline.
        - No blocks: return text as-is, was_stripped=False.

    Raises:
        FenceStripError: If stripping produces empty/whitespace-only output.
    """
    lines = text.split("\n")
    blocks: list[list[str]] = []  # collected content blocks
    current_block: list[str] | None = None
    depth = 0
    open_backtick_count = 0

    for line in lines:
        is_fence, backtick_count = _is_fence_line(line)

        if is_fence:
            if depth == 0:
                # Opening a new outermost fence
                depth = 1
                open_backtick_count = backtick_count
                current_block = []
            elif depth == 1 and backtick_count >= open_backtick_count:
                # Closing the outermost fence (must have >= same backtick count)
                # Only close if the line has no language tag (closing fences are bare)
                # Actually, closing fences can match with >= backticks regardless
                blocks.append(current_block)
                current_block = None
                depth = 0
                open_backtick_count = 0
            else:
                # We're inside an outermost block but this fence doesn't close it
                # (fewer backticks = nested fence, treat as content)
                if current_block is not None:
                    current_block.append(line)
        else:
            if depth > 0 and current_block is not None:
                # Inside an outermost block — collect as content
                current_block.append(line)

    # Handle unclosed fence: if we have an open block that was never closed,
    # treat it as a valid block (the model may have omitted the closing fence)
    if current_block is not None and depth > 0:
        blocks.append(current_block)

    if not blocks:
        # No fences found — return text unchanged
        return text, False

    # Join each block's lines, then join blocks with a single newline
    block_contents = ["\n".join(block) for block in blocks]
    result = "\n".join(block_contents)

    # Check for empty/whitespace-only result
    if not result.strip():
        raise FenceStripError(
            "Stripping produced empty output — "
            "fenced blocks contained only whitespace"
        )

    return result, True
