# Feature: local-coder-workflow-improvements, Property 3: Delegation Hint Format and Tag Selection
"""Property test: For any subset of 1-4 tags from the valid tag set and any valid
complexity tier, the delegation hint produced by _build_delegation_hint SHALL match
the format '[local-coder: --tags <T1> ... <Tn> --complexity (simple|complex|prose)]'
with an optional '--context ...' suffix. Every tag in the output SHALL be from the
valid tag set.

**Validates: Requirements 2.1, 2.2**
"""

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.task_annotator import TaskAnnotator

VALID_TAGS = [
    "code", "test", "api", "security", "refactor",
    "optimization", "docs", "git", "release", "new-project", "review",
]

VALID_TIERS = ["simple", "complex", "prose"]

# Regex matching the expected delegation hint format
_HINT_PATTERN = re.compile(
    r"^\[local-coder: --tags .+ --complexity (simple|complex|prose)(\s+--context .+)?\]$"
)


@settings(max_examples=100)
@given(
    tags=st.lists(
        st.sampled_from(VALID_TAGS), min_size=1, max_size=4, unique=True
    ),
    tier=st.sampled_from(VALID_TIERS),
    context_files=st.lists(
        st.from_regex(r"[a-z_]+/[a-z_]+\.py", fullmatch=True),
        min_size=0,
        max_size=5,
    ),
)
def test_delegation_hint_format_and_tag_selection(
    tags: list[str], tier: str, context_files: list[str]
) -> None:
    """For any valid tag subset and tier, the hint matches the expected format
    and all tags in the output are from the valid tag set."""
    # Create TaskAnnotator with a dummy project root (no file I/O needed for
    # _build_delegation_hint when context_files don't exist on disk — token
    # estimate will be 0 which is below 80% threshold)
    annotator = TaskAnnotator(project_root=Path("/tmp/dummy_project"))

    result = annotator._build_delegation_hint(tags, tier, context_files)

    # With ≤5 context_files and a large context window (default 32768),
    # the hint should never be None or cloud-only
    assert result is not None, (
        f"Expected a delegation hint but got None for tags={tags}, "
        f"tier={tier}, context_files={context_files}"
    )
    assert result != "[cloud-only: context exceeds local budget]", (
        f"Expected local-coder hint but got cloud-only for tags={tags}, "
        f"tier={tier}, context_files={context_files}"
    )

    # Verify overall format matches the regex
    assert _HINT_PATTERN.match(result), (
        f"Delegation hint does not match expected format.\n"
        f"  Got: {result}\n"
        f"  Expected pattern: {_HINT_PATTERN.pattern}"
    )

    # Extract the tags portion from the hint and verify each tag is valid
    # Format: [local-coder: --tags T1 T2 --complexity tier ...]
    tags_match = re.search(r"--tags (.+?) --complexity", result)
    assert tags_match is not None, f"Could not extract tags from hint: {result}"

    output_tags = tags_match.group(1).split()
    for tag in output_tags:
        assert tag in VALID_TAGS, (
            f"Tag '{tag}' in delegation hint is not in the valid tag set.\n"
            f"  Hint: {result}\n"
            f"  Valid tags: {VALID_TAGS}"
        )

    # Verify the tags in the output match what was passed in
    assert output_tags == tags, (
        f"Output tags don't match input tags.\n"
        f"  Input: {tags}\n"
        f"  Output: {output_tags}"
    )

    # Verify the tier in the output matches what was passed in
    assert f"--complexity {tier}" in result, (
        f"Expected --complexity {tier} in hint but got: {result}"
    )

    # If context_files were provided and non-empty, verify --context is present
    if context_files:
        assert "--context" in result, (
            f"Expected --context in hint when context_files={context_files}, "
            f"but got: {result}"
        )
