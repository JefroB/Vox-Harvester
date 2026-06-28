"""Unit tests for path resolution and template discovery functions.

Tests cover:
- _resolve_shared_path with env var, without env var, with override
- _resolve_project_path with existing and non-existing directory
- _discover_templates with mixed valid/invalid files
- Supported extensions filtering (.md, .py, .ts, .js only)

Requirements: 1.3, 9.1, 9.2, 9.3, 9.4
"""

from pathlib import Path

from local_coder.scaffolding_selector import (
    _discover_templates,
    _resolve_project_path,
    _resolve_shared_path,
)


# --- _resolve_shared_path tests ---


def test_resolve_shared_path_override(tmp_path: Path) -> None:
    """Override path is returned when it exists."""
    override_dir = tmp_path / "my_scaffolding"
    override_dir.mkdir()
    result = _resolve_shared_path(override=override_dir)
    assert result == override_dir


def test_resolve_shared_path_env_var(tmp_path: Path, monkeypatch) -> None:
    """SCAFFOLDING_LIBRARY_PATH env var is used when set and directory exists."""
    env_dir = tmp_path / "env_scaffolding"
    env_dir.mkdir()
    monkeypatch.setenv("SCAFFOLDING_LIBRARY_PATH", str(env_dir))
    result = _resolve_shared_path()
    assert result == env_dir


def test_resolve_shared_path_fallback(tmp_path: Path, monkeypatch) -> None:
    """Falls back to ~/.kiro/scaffolding/ when no env var is set."""
    # Remove env var if present
    monkeypatch.delenv("SCAFFOLDING_LIBRARY_PATH", raising=False)
    # Create the fallback directory
    fallback_dir = tmp_path / ".kiro" / "scaffolding"
    fallback_dir.mkdir(parents=True)
    # Mock Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    result = _resolve_shared_path()
    assert result == fallback_dir


def test_resolve_shared_path_none_when_missing(tmp_path: Path, monkeypatch) -> None:
    """Returns None when no override, no env, and no fallback directory."""
    monkeypatch.delenv("SCAFFOLDING_LIBRARY_PATH", raising=False)
    # Mock Path.home() to a dir without .kiro/scaffolding/
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    result = _resolve_shared_path()
    assert result is None


def test_resolve_shared_path_env_nonexistent_with_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    """When env path doesn't exist but fallback does, uses fallback with warning."""
    monkeypatch.setenv("SCAFFOLDING_LIBRARY_PATH", str(tmp_path / "nonexistent"))
    fallback_dir = tmp_path / ".kiro" / "scaffolding"
    fallback_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    result = _resolve_shared_path()
    assert result == fallback_dir


# --- _resolve_project_path tests ---


def test_resolve_project_path_existing(tmp_path: Path) -> None:
    """Returns the override path when it exists as a directory."""
    project_scaffolding = tmp_path / ".kiro" / "scaffolding"
    project_scaffolding.mkdir(parents=True)
    result = _resolve_project_path(override=project_scaffolding)
    assert result == project_scaffolding


def test_resolve_project_path_nonexistent(tmp_path: Path) -> None:
    """Returns None when override path doesn't exist."""
    nonexistent = tmp_path / "does_not_exist"
    result = _resolve_project_path(override=nonexistent)
    assert result is None


# --- _discover_templates tests ---


def _write_template(path: Path, name: str, tags: list[str]) -> None:
    """Helper: write a template file with valid frontmatter."""
    tags_str = "[" + ", ".join(tags) + "]"
    content = (
        "---\n"
        f"name: {name}\n"
        f"tags: {tags_str}\n"
        "category: test\n"
        "description: A test template\n"
        "---\n"
        "# Body content\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_templates_mixed_files(tmp_path: Path) -> None:
    """Discovers valid templates and skips unsupported/invalid ones.

    Creates:
    - valid .md file with frontmatter → included
    - valid .py file with frontmatter → included
    - .txt file (unsupported extension) → skipped
    - .md file without frontmatter → skipped with warning
    """
    # Valid .md template
    _write_template(tmp_path / "valid.md", "valid-md", ["test", "code"])

    # Valid .py template
    _write_template(tmp_path / "valid.py", "valid-py", ["code"])

    # Unsupported extension (.txt) - should be skipped
    txt_file = tmp_path / "ignored.txt"
    txt_file.write_text(
        "---\nname: ignored\ntags: [test]\ncategory: test\n"
        "description: desc\n---\nbody\n",
        encoding="utf-8",
    )

    # .md file without frontmatter - should be skipped
    no_frontmatter = tmp_path / "no_frontmatter.md"
    no_frontmatter.write_text("# Just a markdown file\nNo frontmatter here.\n", encoding="utf-8")

    templates = _discover_templates(tmp_path, "shared")

    # Only the two valid templates should be returned
    assert len(templates) == 2
    names = {t.name for t in templates}
    assert names == {"valid-md", "valid-py"}

    # Verify source is set correctly
    for t in templates:
        assert t.source == "shared"


def test_discover_templates_extension_filtering(tmp_path: Path) -> None:
    """Only .md, .py, .ts, .js extensions are supported; others are skipped.

    Creates files with extensions: .md, .py, .ts, .js, .txt, .yaml, .json
    All have valid frontmatter. Only the first four should be returned.
    """
    supported = [".md", ".py", ".ts", ".js"]
    unsupported = [".txt", ".yaml", ".json"]

    for ext in supported + unsupported:
        name = f"template{ext.replace('.', '-')}"
        filepath = tmp_path / f"template{ext}"
        _write_template(filepath, name, ["test"])

    templates = _discover_templates(tmp_path, "project")

    assert len(templates) == 4
    returned_extensions = {t.path.suffix for t in templates}
    assert returned_extensions == {".md", ".py", ".ts", ".js"}

    # Verify all have source = "project"
    for t in templates:
        assert t.source == "project"


def test_discover_templates_empty_directory(tmp_path: Path) -> None:
    """Returns empty list when directory has no template files."""
    templates = _discover_templates(tmp_path, "shared")
    assert templates == []


def test_discover_templates_nonexistent_directory(tmp_path: Path) -> None:
    """Returns empty list when directory doesn't exist."""
    nonexistent = tmp_path / "nonexistent"
    templates = _discover_templates(nonexistent, "shared")
    assert templates == []


def test_discover_templates_token_estimate(tmp_path: Path) -> None:
    """Token estimate is computed as len(content) // 4."""
    content = (
        "---\n"
        "name: token-test\n"
        "tags: [test]\n"
        "category: test\n"
        "description: desc\n"
        "---\n"
        "Body content for token estimation\n"
    )
    filepath = tmp_path / "token_test.md"
    filepath.write_text(content, encoding="utf-8")

    templates = _discover_templates(tmp_path, "shared")
    assert len(templates) == 1
    assert templates[0].token_estimate == len(content) // 4


def test_discover_templates_subdirectory_recursion(tmp_path: Path) -> None:
    """Templates in category subdirectories are discovered recursively."""
    subdir = tmp_path / "test-patterns"
    subdir.mkdir()
    _write_template(subdir / "nested.md", "nested-template", ["test"])

    deep_subdir = tmp_path / "code-patterns" / "deep"
    deep_subdir.mkdir(parents=True)
    _write_template(deep_subdir / "deep.py", "deep-template", ["code"])

    templates = _discover_templates(tmp_path, "shared")
    assert len(templates) == 2
    names = {t.name for t in templates}
    assert names == {"nested-template", "deep-template"}
