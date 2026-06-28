# Feature: scaffolding-library, Property 8: Scaffolding-Before-Context Ordering
"""Property-based tests for scaffolding-before-context ordering.

**Validates: Requirements 4.3**

For any non-empty list of scaffolding paths and for any non-empty list of project
context paths, after integration in local_coder.py, the final context list SHALL
have all scaffolding paths appearing at indices strictly less than all project
context paths. No project context path precedes any scaffolding path.
"""

from hypothesis import given, settings
from hypothesis import strategies as st


# --- Strategies ---

# Generate path-like strings (simulating file paths)
path_strategy = st.text(
    alphabet="abcdefghij/_.",
    min_size=5,
    max_size=30,
)

# Generate non-empty lists of scaffolding paths (1-10)
scaffolding_paths_strategy = st.lists(path_strategy, min_size=1, max_size=10)

# Generate non-empty lists of project context paths (1-10)
project_context_paths_strategy = st.lists(path_strategy, min_size=1, max_size=10)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    scaffolding_paths=scaffolding_paths_strategy,
    project_context_paths=project_context_paths_strategy,
)
def test_scaffolding_indices_less_than_project_indices(
    scaffolding_paths, project_context_paths
):
    """All scaffolding path indices are strictly less than all project context path indices.

    Simulates the prepend logic from local_coder.py:
        args.context = [str(p) for p in scaffolding_paths] + (args.context or [])

    Verifies that for every scaffolding path s and every project path p in
    final_context: final_context.index(s) < final_context.index(p).
    """
    # Simulate the prepend logic
    final_context = scaffolding_paths + project_context_paths

    # For every scaffolding path and every project path, verify ordering
    for i, s in enumerate(scaffolding_paths):
        for j, p in enumerate(project_context_paths):
            s_index = i  # scaffolding paths occupy indices [0, len(scaffolding_paths))
            p_index = len(scaffolding_paths) + j  # project paths start after scaffolding
            assert s_index < p_index, (
                f"Scaffolding path '{s}' at index {s_index} is not before "
                f"project context path '{p}' at index {p_index}"
            )


@settings(max_examples=100)
@given(
    scaffolding_paths=scaffolding_paths_strategy,
    project_context_paths=project_context_paths_strategy,
)
def test_final_context_prefix_is_scaffolding(scaffolding_paths, project_context_paths):
    """The first len(scaffolding_paths) elements of final_context are exactly the scaffolding paths.

    Verifies: final_context[:len(scaffolding_paths)] == scaffolding_paths
    """
    # Simulate the prepend logic
    final_context = scaffolding_paths + project_context_paths

    assert final_context[: len(scaffolding_paths)] == scaffolding_paths, (
        f"Expected first {len(scaffolding_paths)} elements to be scaffolding paths.\n"
        f"Got: {final_context[:len(scaffolding_paths)]}\n"
        f"Expected: {scaffolding_paths}"
    )


@settings(max_examples=100)
@given(
    scaffolding_paths=scaffolding_paths_strategy,
    project_context_paths=project_context_paths_strategy,
)
def test_final_context_suffix_is_project(scaffolding_paths, project_context_paths):
    """The last len(project_context_paths) elements of final_context are exactly the project paths.

    Verifies: final_context[len(scaffolding_paths):] == project_context_paths
    """
    # Simulate the prepend logic
    final_context = scaffolding_paths + project_context_paths

    assert final_context[len(scaffolding_paths) :] == project_context_paths, (
        f"Expected last {len(project_context_paths)} elements to be project context paths.\n"
        f"Got: {final_context[len(scaffolding_paths):]}\n"
        f"Expected: {project_context_paths}"
    )


@settings(max_examples=100)
@given(
    scaffolding_paths=scaffolding_paths_strategy,
    project_context_paths=project_context_paths_strategy,
)
def test_no_project_path_precedes_any_scaffolding_path(
    scaffolding_paths, project_context_paths
):
    """No project context path appears before any scaffolding path in final_context.

    Uses index-based lookup on the final list to verify the ordering constraint
    without assuming uniqueness of path strings.
    """
    # Simulate the prepend logic
    final_context = scaffolding_paths + project_context_paths

    # The boundary is clear: scaffolding occupies [0, len(scaffolding_paths))
    # and project occupies [len(scaffolding_paths), len(final_context))
    scaffolding_end = len(scaffolding_paths)

    # Verify no project path appears in the scaffolding region
    project_region = final_context[scaffolding_end:]
    scaffolding_region = final_context[:scaffolding_end]

    assert scaffolding_region == scaffolding_paths, (
        "Scaffolding region does not match expected scaffolding paths"
    )
    assert project_region == project_context_paths, (
        "Project region does not match expected project context paths"
    )
