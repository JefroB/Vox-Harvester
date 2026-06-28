"""Unit tests for local_coder/file_tagger.py.

Tests CodeSearch unavailability handling, symbol extraction regex patterns,
file path verification with non-existent paths, deduplication logic,
and the max-5 file tag cap.

Requirements: 5.1, 5.2, 5.5
"""

from pathlib import Path
from unittest.mock import patch

from local_coder.file_tagger import (
    FileTag,
    _extract_camel_case_symbols,
    _extract_file_paths,
    _extract_snake_case_symbols,
    _verify_file_path,
    is_codesearch_available,
    tag_files,
)


def test_codesearch_unavailable_returns_empty(tmp_path: Path, capsys) -> None:
    """When .codesearch/index.db doesn't exist, tag_files() returns [] and logs warning."""
    # tmp_path has no .codesearch/index.db
    result = tag_files("Refactor MyClass in src/utils.py", tmp_path)

    assert result == []
    captured = capsys.readouterr()
    assert "CodeSearch unavailable" in captured.err


def test_is_codesearch_available_false(tmp_path: Path) -> None:
    """is_codesearch_available returns False when index.db is missing."""
    assert is_codesearch_available(tmp_path) is False


def test_is_codesearch_available_true(tmp_path: Path) -> None:
    """is_codesearch_available returns True when index.db exists."""
    codesearch_dir = tmp_path / ".codesearch"
    codesearch_dir.mkdir()
    (codesearch_dir / "index.db").write_text("dummy")

    assert is_codesearch_available(tmp_path) is True


def test_camel_case_extraction() -> None:
    """Verify _extract_camel_case_symbols picks up CamelCase identifiers."""
    text = "Refactor TaskRunner and update ConfigManager in the codebase"
    symbols = _extract_camel_case_symbols(text)

    assert "TaskRunner" in symbols
    assert "ConfigManager" in symbols


def test_camel_case_extraction_ignores_single_word() -> None:
    """Single capitalized words are not CamelCase identifiers."""
    text = "Update the Database and fix the Server"
    symbols = _extract_camel_case_symbols(text)

    # "Database" and "Server" are single words, not multi-hump CamelCase
    assert "Database" not in symbols
    assert "Server" not in symbols


def test_snake_case_extraction() -> None:
    """Verify _extract_snake_case_symbols picks up snake_case identifiers with underscores."""
    text = "Fix the get_user_name function and update parse_config"
    symbols = _extract_snake_case_symbols(text)

    assert "get_user_name" in symbols
    assert "parse_config" in symbols


def test_snake_case_extraction_excludes_common_words() -> None:
    """Common English words without underscores are filtered out."""
    text = "this should not match any common words like name or time"
    symbols = _extract_snake_case_symbols(text)

    # Words without underscores that are in the exclusion list should be filtered
    assert "name" not in symbols
    assert "time" not in symbols


def test_snake_case_extraction_requires_underscore() -> None:
    """Snake case extraction requires an underscore to distinguish from regular words."""
    text = "update the handler and call the function"
    symbols = _extract_snake_case_symbols(text)

    # None of these should match since they lack underscores
    assert "update" not in symbols
    assert "handler" not in symbols
    assert "function" not in symbols


def test_file_path_extraction() -> None:
    """Verify _extract_file_paths picks up paths with slashes and extensions."""
    text = "Edit src/utils/helpers.py and local_coder/file_tagger.py"
    paths = _extract_file_paths(text)

    assert "src/utils/helpers.py" in paths
    assert "local_coder/file_tagger.py" in paths


def test_file_path_extraction_backslash() -> None:
    """Backslash paths are normalized to forward slashes."""
    text = r"Check src\models\user.ts for the issue"
    paths = _extract_file_paths(text)

    assert "src/models/user.ts" in paths


def test_file_path_extraction_ignores_non_source_extensions() -> None:
    """Paths with non-source extensions are not extracted."""
    text = "Open the file at docs/image.bmp"
    paths = _extract_file_paths(text)

    # .bmp is not in _SOURCE_EXTENSIONS
    assert len(paths) == 0


def test_verify_nonexistent_path(tmp_path: Path) -> None:
    """_verify_file_path returns None for paths that don't exist."""
    result = _verify_file_path("nonexistent/file.py", tmp_path)
    assert result is None


def test_verify_existing_path(tmp_path: Path) -> None:
    """_verify_file_path returns a FileTag for paths that exist."""
    # Create a file
    sub = tmp_path / "src"
    sub.mkdir()
    target = sub / "main.py"
    target.write_text("# code")

    result = _verify_file_path("src/main.py", tmp_path)
    assert result is not None
    assert result.file_path == str(target)
    assert result.line_range is None


def test_deduplication(tmp_path: Path) -> None:
    """Same file path found via multiple routes only appears once in results."""
    # Create the codesearch index so tag_files doesn't bail early
    codesearch_dir = tmp_path / ".codesearch"
    codesearch_dir.mkdir()
    (codesearch_dir / "index.db").write_text("dummy")

    # Create a file that both path extraction and codesearch would find
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    target_file = src_dir / "handler.py"
    target_file.write_text("class RequestHandler:\n    pass\n")

    # Mock codesearch to return the same file for symbol queries
    def mock_query(symbol, workspace_root):
        return FileTag(file_path=str(target_file))

    # Task mentions both a file path and a CamelCase symbol that resolves to same file
    task = "Fix src/handler.py and refactor RequestHandler"

    with patch("local_coder.file_tagger._query_codesearch", side_effect=mock_query):
        results = tag_files(task, tmp_path)

    # The file should appear only once despite being found via path AND symbol
    file_paths = [tag.file_path for tag in results]
    assert file_paths.count(str(target_file)) == 1


def test_max_5_cap(tmp_path: Path) -> None:
    """Even with many symbols, result is capped at 5."""
    # Create the codesearch index
    codesearch_dir = tmp_path / ".codesearch"
    codesearch_dir.mkdir()
    (codesearch_dir / "index.db").write_text("dummy")

    # Create 10 different files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    created_files = []
    for i in range(10):
        f = src_dir / f"module_{i}.py"
        f.write_text(f"# module {i}")
        created_files.append(str(f))

    # Counter to return a different file for each call
    call_count = {"n": 0}

    def mock_query(symbol, workspace_root):
        idx = call_count["n"] % len(created_files)
        call_count["n"] += 1
        return FileTag(file_path=created_files[idx])

    # Task with many CamelCase symbols that would each resolve to a different file
    task = (
        "Refactor ClassOne ClassTwo ClassThree ClassFour ClassFive "
        "ClassSix ClassSeven ClassEight ClassNine ClassTen"
    )

    with patch("local_coder.file_tagger._query_codesearch", side_effect=mock_query):
        results = tag_files(task, tmp_path)

    assert len(results) <= 5
