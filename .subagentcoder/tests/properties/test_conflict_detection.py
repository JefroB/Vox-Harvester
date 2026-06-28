"""Property tests for conflict detection (local_coder/conflict_detector.py)."""

import os
import string
import tempfile
from typing import List

import hypothesis.strategies as st
from hypothesis import given, settings

from local_coder.conflict_detector import TaskSpec, detect_output_conflicts


@given(
    task_ids=st.lists(
        st.text(min_size=1, alphabet=string.ascii_letters + string.digits),
        min_size=2,
        max_size=10,
    ),
    path=st.text(min_size=1, alphabet=string.ascii_letters + string.digits),
)
@settings(max_examples=100)
def test_dispatch_warning_format(task_ids: List[str], path: str) -> None:
    """Feature: local-coder-reliability, Property 3: Dispatch Warning Format

    Validates: Requirements 5.3
    """
    # Build TaskSpec objects that all share the same --output path
    tasks = [TaskSpec(task_id=tid, command_args=["--output", path]) for tid in task_ids]

    result = detect_output_conflicts(tasks)

    # a) The warnings list is non-empty (we have 2+ tasks sharing a path)
    assert len(result.warnings) > 0, "Expected at least one warning for conflicting tasks"

    for warning in result.warnings:
        # b) Each warning starts with the expected prefix
        assert warning.startswith("[DISPATCH WARN] Serializing tasks "), (
            f"Warning does not start with expected prefix: {warning!r}"
        )

        # c) Each warning contains em-dash separator (U+2014, not hyphen)
        assert " \u2014 shared output file: " in warning, (
            f"Warning missing em-dash separator: {warning!r}"
        )

        # d) The task IDs in the warning match the actual conflicting task IDs
        # The format uses Python's list repr: ['id1', 'id2']
        expected_repr = repr(task_ids)
        expected_warning = (
            f"[DISPATCH WARN] Serializing tasks {expected_repr}"
            f" \u2014 shared output file: "
        )
        assert warning.startswith(expected_warning), (
            f"Warning task IDs don't match.\n"
            f"  Expected prefix: {expected_warning!r}\n"
            f"  Got: {warning!r}"
        )


# Strategies for generating path transformations
_path_transform = st.sampled_from([
    "dot_prefix",       # ./dir/file  vs  dir/file
    "dotdot_roundtrip", # dir/../dir/file  vs  dir/file
    "double_dotdot",    # dir/sub/../sub/file  vs  dir/sub/file (both with ..)
])


@given(
    dirname=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
    filename=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
    transform=_path_transform,
)
@settings(max_examples=100)
def test_path_canonicalization_equivalence(dirname, filename, transform):
    """Feature: local-coder-reliability, Property 2: Path Canonicalization Equivalence

    Validates: Requirements 5.5

    For any two path strings referring to the same location (via .., .,
    different relative notation), conflict detection identifies them as
    targeting the same file.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the subdirectory so Path.resolve() can canonicalize
        subdir = os.path.join(temp_dir, dirname)
        os.makedirs(subdir, exist_ok=True)

        target_file = os.path.join(subdir, filename)

        # Build two different path representations for the same file
        if transform == "dot_prefix":
            # <temp>/./dir/file vs <temp>/dir/file
            path1 = os.path.join(temp_dir, ".", dirname, filename)
            path2 = os.path.join(temp_dir, dirname, filename)
        elif transform == "dotdot_roundtrip":
            # <temp>/dir/../dir/file vs <temp>/dir/file
            path1 = os.path.join(temp_dir, dirname, "..", dirname, filename)
            path2 = target_file
        else:  # double_dotdot
            # <temp>/dir/../dir/file vs <temp>/./dir/file
            path1 = os.path.join(temp_dir, dirname, "..", dirname, filename)
            path2 = os.path.join(temp_dir, ".", dirname, filename)

        task1 = TaskSpec(task_id="task1", command_args=["--output", path1])
        task2 = TaskSpec(task_id="task2", command_args=["--output", path2])

        result = detect_output_conflicts([task1, task2])

        # Both tasks target the same canonical path, so they should be serialized
        assert len(result.serial_chains) == 1, (
            f"Expected 1 serial chain but got {len(result.serial_chains)}. "
            f"path1={path1!r}, path2={path2!r}, transform={transform}"
        )
        assert len(result.parallel_groups) == 0, (
            f"Expected 0 parallel groups but got {len(result.parallel_groups)}. "
            f"path1={path1!r}, path2={path2!r}"
        )
        chain_ids = {t.task_id for t in result.serial_chains[0]}
        assert chain_ids == {"task1", "task2"}
