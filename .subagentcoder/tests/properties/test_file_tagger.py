# Feature: local-coder-task-intelligence, Property 9: FileTag structure validity
# Feature: local-coder-task-intelligence, Property 10: File tag count is capped at 5
"""Property-based tests for the File Tagger module.

**Validates: Requirements 5.3, 5.6**

Property 9: For any output from `tag_files()`, every element SHALL be a FileTag
where `file_path` is a non-empty string, and `line_range` is either None or a
tuple (start, end) with start ≤ end and both > 0.

Property 10: For any task description (regardless of how many symbols or file
paths it contains), `tag_files()` SHALL return a list with at most 5 elements.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.file_tagger import FileTag, tag_files


# --- Strategies ---

# Generate task descriptions with many potential symbols and file paths
# to exercise the cap and structure validation logic.

# CamelCase symbols that will be extracted by the tagger
_camel_case_symbols = st.sampled_from([
    "FileParser", "CodeSearch", "TaskRunner", "TestSuite", "DataLoader",
    "EventHandler", "ModelFactory", "ConfigManager", "LogWriter", "ApiClient",
    "UserSession", "TokenCache", "BuildStep", "ReportGenerator", "ErrorHandler",
])

# snake_case symbols that will be extracted by the tagger
_snake_case_symbols = st.sampled_from([
    "parse_file", "run_task", "load_data", "handle_event", "create_model",
    "write_log", "build_config", "compute_hash", "validate_input", "fetch_result",
    "process_queue", "merge_data", "split_token", "emit_signal", "close_connection",
])

# File path references that will be extracted by the tagger
_file_paths = st.sampled_from([
    "src/main.py", "lib/utils.ts", "tests/test_core.py", "src/api/handler.js",
    "config/settings.yaml", "src/models/user.py", "pkg/server.go",
    "app/controllers/auth.rb", "src/db/migrations.sql", "tools/build.sh",
])


def _build_task_with_many_symbols(symbols, paths):
    """Build a task description containing many symbols and file paths."""
    parts = list(symbols) + list(paths)
    return "Refactor " + " and update ".join(parts) + " to improve performance"


# Strategy that generates tasks with many symbols (more than 5 potential matches)
task_with_many_references = st.builds(
    _build_task_with_many_symbols,
    symbols=st.lists(_camel_case_symbols, min_size=3, max_size=8),
    paths=st.lists(_file_paths, min_size=3, max_size=8),
)

# Strategy for arbitrary task descriptions (including edge cases)
arbitrary_task_descriptions = st.one_of(
    st.text(min_size=0, max_size=500),
    task_with_many_references,
    st.just(""),
    st.just("Fix the bug"),
    st.just("Update FileParser and CodeSearch and TaskRunner and TestSuite "
            "and DataLoader and EventHandler and ModelFactory"),
)


def _mock_codesearch_result(symbol, workspace_root):
    """Mock CodeSearch query returning a FileTag for any symbol."""
    # Simulate finding the symbol in a file
    return FileTag(
        file_path=str(workspace_root / f"src/{symbol.lower()}.py"),
        line_range=(1, 20),
    )


# --- Property Tests ---


@settings(max_examples=100)
@given(task=arbitrary_task_descriptions)
def test_property_9_file_tag_structure_validity(task):
    """Property 9: For any output from tag_files(), every element SHALL be a
    FileTag where file_path is a non-empty string, and line_range is either
    None or a tuple (start, end) with start ≤ end and both > 0.

    **Validates: Requirements 5.3**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # Create the .codesearch/index.db so is_codesearch_available returns True
        codesearch_dir = workspace / ".codesearch"
        codesearch_dir.mkdir()
        (codesearch_dir / "index.db").touch()

        # Mock _query_codesearch to return valid FileTags without needing
        # actual codesearch binary
        with patch(
            "local_coder.file_tagger._query_codesearch",
            side_effect=lambda sym, root: _mock_codesearch_result(sym, root),
        ):
            results = tag_files(task, workspace)

        # Validate structure of every returned FileTag
        assert isinstance(results, list)
        for tag in results:
            assert isinstance(tag, FileTag)
            # file_path must be a non-empty string
            assert isinstance(tag.file_path, str)
            assert len(tag.file_path) > 0

            # line_range must be None or a tuple (start, end) with start <= end, both > 0
            if tag.line_range is not None:
                assert isinstance(tag.line_range, tuple)
                assert len(tag.line_range) == 2
                start, end = tag.line_range
                assert isinstance(start, int)
                assert isinstance(end, int)
                assert start > 0, f"start must be > 0, got {start}"
                assert end > 0, f"end must be > 0, got {end}"
                assert start <= end, f"start ({start}) must be <= end ({end})"


@settings(max_examples=100)
@given(task=task_with_many_references)
def test_property_10_file_tag_count_capped_at_5(task):
    """Property 10: For any task description (regardless of how many symbols or
    file paths it contains), tag_files() SHALL return a list with at most 5 elements.

    **Validates: Requirements 5.6**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # Create the .codesearch/index.db so is_codesearch_available returns True
        codesearch_dir = workspace / ".codesearch"
        codesearch_dir.mkdir()
        (codesearch_dir / "index.db").touch()

        # Create actual files so _verify_file_path finds them
        src_dir = workspace / "src"
        src_dir.mkdir()
        for path in [
            "src/main.py", "lib/utils.ts", "tests/test_core.py",
            "src/api/handler.js", "config/settings.yaml", "src/models/user.py",
            "pkg/server.go", "app/controllers/auth.rb", "src/db/migrations.sql",
            "tools/build.sh",
        ]:
            file_path = workspace / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()

        # Mock _query_codesearch to return valid FileTags for every symbol
        with patch(
            "local_coder.file_tagger._query_codesearch",
            side_effect=lambda sym, root: _mock_codesearch_result(sym, root),
        ):
            results = tag_files(task, workspace)

        # The cap must always hold regardless of input size
        assert isinstance(results, list)
        assert len(results) <= 5, (
            f"Expected at most 5 file tags, got {len(results)} for task: {task[:100]}..."
        )
