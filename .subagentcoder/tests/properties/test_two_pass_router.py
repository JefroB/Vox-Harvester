# Feature: local-coder-reliability, Properties 7 & 8: Two-Pass Routing
"""Property tests for two_pass_router module.

Property 7: Two-Pass Routing Keyword Detection (Requirements 8.1, 8.2, 8.3, 8.4)
Property 8: Routing Log Format (Requirements 8.6)
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.two_pass_router import (
    PROSE_CODE_INDICATORS,
    detect_two_pass,
)

# --- Strategies ---

# Valid trigger keyword combinations from TWO_PASS_TRIGGERS
_keyword_triggers = st.sampled_from([
    (["strategy", "example"], "Req 8.1"),
    (["strategy", "code snippet"], "Req 8.1"),
    (["documentation", "implementation"], "Req 8.2"),
    (["template", "guidance", "pattern"], "Req 8.3"),
])

# Random surrounding text that won't accidentally contain trigger keywords
_safe_padding = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        blacklist_characters="",
    ),
    min_size=0,
    max_size=30,
)

# Prose+code indicators for .md output path testing (Req 8.4)
_prose_code_indicator = st.sampled_from(PROSE_CODE_INDICATORS)


# --- Property 7: Two-Pass Routing Keyword Detection ---


# Validates: Requirements 8.1, 8.2, 8.3
@settings(max_examples=100)
@given(
    trigger=_keyword_triggers,
    prefix=_safe_padding,
    suffix=_safe_padding,
)
def test_keyword_combination_triggers_two_pass(
    trigger: tuple[list[str], str],
    prefix: str,
    suffix: str,
) -> None:
    """Feature: local-coder-reliability, Property 7: Two-Pass Routing Keyword Detection

    For any task description containing a valid trigger keyword combination,
    routing returns is_two_pass=True and matched_keywords is non-empty.
    """
    keywords, _req_label = trigger
    # Build task description embedding all required keywords with padding
    task_parts = [prefix]
    for kw in keywords:
        task_parts.append(kw)
    task_parts.append(suffix)
    task = " ".join(task_parts)

    result = detect_two_pass(task)

    assert result.is_two_pass is True, (
        f"Expected is_two_pass=True for keywords {keywords} in task: {task!r}"
    )
    assert len(result.matched_keywords) > 0, (
        f"Expected non-empty matched_keywords for keywords {keywords}"
    )


# Validates: Requirements 8.4
@settings(max_examples=100)
@given(
    indicator=_prose_code_indicator,
    prefix=_safe_padding,
    suffix=_safe_padding,
)
def test_md_output_with_prose_code_indicator_triggers_two_pass(
    indicator: str,
    prefix: str,
    suffix: str,
) -> None:
    """Feature: local-coder-reliability, Property 7: Two-Pass Routing Keyword Detection

    For any .md output path combined with a prose+code indicator in the task,
    routing returns is_two_pass=True.
    """
    task = f"{prefix} {indicator} {suffix}"
    output_path = "docs/output.md"

    result = detect_two_pass(task, output_path=output_path)

    assert result.is_two_pass is True, (
        f"Expected is_two_pass=True for indicator {indicator!r} "
        f"with .md output path, task: {task!r}"
    )
    assert len(result.matched_keywords) > 0, (
        f"Expected non-empty matched_keywords for indicator {indicator!r}"
    )



