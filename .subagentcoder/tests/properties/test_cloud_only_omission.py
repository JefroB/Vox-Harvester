# Feature: local-coder-workflow-improvements, Property 5: Delegation Hint Omission for Cloud-Only Tasks
"""Property test: When a task has too many context files (>5) or its estimated
prompt tokens exceed 80% of the context window, the delegation hint is either
omitted (None) or replaced with a cloud-only annotation.

**Validates: Requirements 2.4, 2.6**
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.task_annotator import TaskAnnotator


@settings(max_examples=50)
@given(
    context_files=st.lists(
        st.from_regex(r"[a-z_]+/[a-z_]+\.py", fullmatch=True),
        min_size=6,
        max_size=20,
    ),
)
def test_omitted_when_too_many_files(context_files: list[str]) -> None:
    """When context_files has more than 5 entries, _build_delegation_hint returns None.

    Requirement 2.4: Tasks requiring 3+ existing files for correct output are
    cloud-only. The implementation threshold is >5 context files → omit hint entirely.
    """
    annotator = TaskAnnotator(project_root=Path("/tmp/dummy_project"))

    result = annotator._build_delegation_hint(
        tags=["code"], tier="simple", context_files=context_files
    )

    assert result is None, (
        f"Expected None for {len(context_files)} context files (>5), "
        f"but got: {result!r}"
    )


@settings(max_examples=50)
@given(
    file_count=st.integers(min_value=1, max_value=5),
)
def test_cloud_only_when_exceeds_budget(file_count: int) -> None:
    """When estimated tokens exceed 80% of context_window, returns cloud-only annotation.

    Requirement 2.6: If estimated prompt size exceeds 80% of context_window,
    the hint becomes '[cloud-only: context exceeds local budget]'.

    Uses context_window=100 so 80% threshold = 80 tokens = 320 characters of files.
    Creates files on disk with enough content to exceed this threshold.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # context_window=100 → threshold is 80 tokens → 320 chars
        annotator = TaskAnnotator(project_root=tmp_path, context_window=100)

        # Create files with enough total content to exceed 320 chars
        # Each file gets 400 // file_count chars (ensures total > 320)
        chars_per_file = 400 // file_count + 1
        context_files = []
        for i in range(file_count):
            file_path = tmp_path / f"big_file_{i}.py"
            file_path.write_text("x" * chars_per_file, encoding="utf-8")
            context_files.append(f"big_file_{i}.py")

        result = annotator._build_delegation_hint(
            tags=["code"], tier="simple", context_files=context_files
        )

        assert result == "[cloud-only: context exceeds local budget]", (
            f"Expected cloud-only annotation when tokens exceed 80% of context_window, "
            f"but got: {result!r} "
            f"(files={file_count}, chars_per_file={chars_per_file}, "
            f"total_chars={chars_per_file * file_count}, "
            f"estimated_tokens={chars_per_file * file_count // 4}, "
            f"threshold=80)"
        )


@settings(max_examples=50)
@given(
    context_files=st.lists(
        st.from_regex(r"[a-z_]+/[a-z_]+\.py", fullmatch=True),
        min_size=0,
        max_size=5,
    ),
)
def test_normal_hint_when_within_limits(context_files: list[str]) -> None:
    """When context_files ≤5 and tokens within budget, returns a normal hint.

    With the default context_window of 32768 and files that don't exist on disk
    (so their size is 0), the token estimate will be well below the 80% threshold.
    The result should be a valid local-coder hint, not None or cloud-only.
    """
    annotator = TaskAnnotator(
        project_root=Path("/tmp/dummy_project"), context_window=32768
    )

    result = annotator._build_delegation_hint(
        tags=["code"], tier="simple", context_files=context_files
    )

    assert result is not None, (
        f"Expected a normal delegation hint for {len(context_files)} context files "
        f"(≤5) but got None"
    )
    assert not result.startswith("[cloud-only"), (
        f"Expected a normal delegation hint but got cloud-only annotation: {result!r}"
    )
