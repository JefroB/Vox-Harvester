"""Integration tests for scaffolding CLI flags in local_coder.py.

Tests cover:
- --scaffolding flag triggers selector and injects paths into context
- --list-scaffolding produces expected output format and exits
- --scaffolding-budget overrides default 4000-token budget
- --scaffolding with explicit template names resolves to paths directly
- Interaction with existing --context and --tags flags

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CODER_SCRIPT = WORKSPACE_ROOT / ".kiro" / "scripts" / "local_coder.py"


def _create_template(directory: Path, name: str, tags: list[str],
                     category: str = "test-skeleton", complexity: str = "any",
                     priority: int = 0, body: str = "# Template body\n") -> Path:
    """Create a scaffolding template file with valid frontmatter.

    Returns the path to the created file.
    """
    tags_str = "[" + ", ".join(tags) + "]"
    content = (
        "---\n"
        f"name: \"{name}\"\n"
        f"tags: {tags_str}\n"
        f"category: \"{category}\"\n"
        f"complexity: \"{complexity}\"\n"
        f"description: \"Template {name} for testing\"\n"
        f"priority: {priority}\n"
        "---\n"
        f"{body}"
    )
    filepath = directory / f"{name}.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    return filepath


def _run_local_coder(args: list[str], env_overrides: dict | None = None,
                     timeout: int = 30) -> subprocess.CompletedProcess:
    """Run local_coder.py with the given arguments.

    Returns the CompletedProcess result.
    """
    env = os.environ.copy()
    # Ensure no pre-existing scaffolding env var interferes
    env.pop("SCAFFOLDING_LIBRARY_PATH", None)
    env.pop("SCAFFOLDING_TOKEN_BUDGET", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    if env_overrides:
        env.update(env_overrides)

    cmd = [sys.executable, str(LOCAL_CODER_SCRIPT)] + args

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(WORKSPACE_ROOT),
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    return result


# --- Test: --list-scaffolding flag ---


class TestListScaffoldingFlag:
    """Tests for the --list-scaffolding flag (Requirement 7.1)."""

    def test_list_scaffolding_shows_templates(self, tmp_path: Path) -> None:
        """--list-scaffolding lists available templates with metadata.

        Verifies output contains: name, category, tags, complexity, source.
        """
        scaffolding_dir = tmp_path / "scaffolding"
        category_dir = scaffolding_dir / "test-patterns"
        category_dir.mkdir(parents=True)
        _create_template(category_dir, "my-test-skeleton", ["test", "property"],
                         category="test-skeleton", complexity="any")

        result = _run_local_coder(
            ["--list-scaffolding"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout
        assert "my-test-skeleton" in output
        assert "test-skeleton" in output
        assert "test" in output
        assert "property" in output
        assert "shared" in output

    def test_list_scaffolding_exits_without_task(self, tmp_path: Path) -> None:
        """--list-scaffolding exits with code 0 without requiring --task."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "dummy", ["test"])

        result = _run_local_coder(
            ["--list-scaffolding"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0

    def test_list_scaffolding_empty_library(self, tmp_path: Path) -> None:
        """--list-scaffolding with empty directory shows 'no templates' message."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()

        result = _run_local_coder(
            ["--list-scaffolding"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0
        assert "No scaffolding templates found" in result.stdout

    def test_list_scaffolding_with_tags_filter(self, tmp_path: Path) -> None:
        """--list-scaffolding --tags filters templates to matching tags only."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "test-helper", ["test", "code"])
        _create_template(scaffolding_dir, "api-pattern", ["api", "code"])

        result = _run_local_coder(
            ["--list-scaffolding", "--tags", "api"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0
        assert "api-pattern" in result.stdout
        assert "test-helper" not in result.stdout


# --- Test: --scaffolding flag auto-select ---


class TestScaffoldingAutoSelect:
    """Tests for --scaffolding flag with auto-selection (Requirement 6.1, 6.2)."""

    def test_scaffolding_auto_select_with_dry_run(self, tmp_path: Path) -> None:
        """--scaffolding auto-selects templates and injects them into context.

        Uses --dry-run to avoid needing Ollama. Checks stderr for [SCAFFOLD]
        report line confirming selection.
        """
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "code-helper", ["code", "test"],
                         priority=5, body="def helper(): pass\n" * 20)

        result = _run_local_coder(
            ["--task", "Write a test helper", "--scaffolding",
             "--tags", "code", "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Check stderr for scaffold selection report
        assert "[SCAFFOLD] Selected 1 template(s): code-helper" in result.stderr

    def test_scaffolding_injects_content_into_prompt(self, tmp_path: Path) -> None:
        """Selected scaffolding content appears in the dry-run prompt output."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        body_marker = "UNIQUE_SCAFFOLDING_MARKER_12345"
        _create_template(scaffolding_dir, "marker-template", ["code"],
                         body=f"# {body_marker}\n" * 10)

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding",
             "--tags", "code", "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # The template content should appear in the dry-run stdout prompt
        assert body_marker in result.stdout

    def test_scaffolding_no_match_returns_silently(self, tmp_path: Path) -> None:
        """When no templates match task tags, no error is emitted."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "api-template", ["api", "rest"])

        result = _run_local_coder(
            ["--task", "Write tests", "--scaffolding",
             "--tags", "test", "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # No [SCAFFOLD] Selected line since nothing matched
        assert "[SCAFFOLD] Selected" not in result.stderr


# --- Test: --scaffolding-budget flag ---


class TestScaffoldingBudget:
    """Tests for --scaffolding-budget flag (Requirement 6.3)."""

    def test_budget_limits_template_selection(self, tmp_path: Path) -> None:
        """--scaffolding-budget limits which templates are included.

        Creates a template with enough content to exceed a small budget,
        verifying it gets excluded.
        """
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()

        # This template will have ~500 tokens (2000 chars / 4)
        large_body = "x" * 2000 + "\n"
        _create_template(scaffolding_dir, "large-template", ["code"],
                         body=large_body, priority=10)

        # Small template that fits in a 100-token budget
        small_body = "y" * 100 + "\n"
        _create_template(scaffolding_dir, "small-template", ["code"],
                         body=small_body, priority=5)

        # Budget of 100 tokens should exclude the large template
        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding",
             "--tags", "code", "--scaffolding-budget", "100",
             "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # The large template (ranked first due to priority=10) exceeds budget
        # so nothing should be selected since greedy-break stops at first that doesn't fit
        assert "large-template" not in result.stderr or "[SCAFFOLD] Selected" not in result.stderr

    def test_budget_allows_small_templates(self, tmp_path: Path) -> None:
        """A generous budget allows templates through."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()

        small_body = "# small\n" * 5
        _create_template(scaffolding_dir, "tiny-template", ["code"],
                         body=small_body)

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding",
             "--tags", "code", "--scaffolding-budget", "50000",
             "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "[SCAFFOLD] Selected 1 template(s): tiny-template" in result.stderr


# --- Test: --scaffolding with explicit template names ---


class TestScaffoldingExplicitNames:
    """Tests for --scaffolding with explicit names (Requirement 6.4)."""

    def test_explicit_name_resolves_to_path(self, tmp_path: Path) -> None:
        """--scaffolding <name> resolves a named template directly."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        body_marker = "EXPLICIT_RESOLVE_MARKER_99999"
        _create_template(scaffolding_dir, "my-explicit-template", ["code"],
                         body=f"# {body_marker}\n" * 5)

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding", "my-explicit-template",
             "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "[SCAFFOLD] Selected 1 template(s): my-explicit-template" in result.stderr
        assert body_marker in result.stdout

    def test_explicit_name_not_found_exits_with_error(self, tmp_path: Path) -> None:
        """--scaffolding with a nonexistent name exits with error."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "existing", ["code"])

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding", "nonexistent-name",
             "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode != 0
        assert "Template not found: nonexistent-name" in result.stderr

    def test_explicit_multiple_names(self, tmp_path: Path) -> None:
        """--scaffolding name1 name2 resolves multiple templates."""
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "template-a", ["code"],
                         body="# Template A body\n" * 3)
        _create_template(scaffolding_dir, "template-b", ["test"],
                         body="# Template B body\n" * 3)

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding", "template-a", "template-b",
             "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "[SCAFFOLD] Selected 2 template(s):" in result.stderr
        assert "template-a" in result.stderr
        assert "template-b" in result.stderr


# --- Test: Interaction with --context and --tags ---


class TestScaffoldingContextInteraction:
    """Tests for scaffolding interaction with --context and --tags flags."""

    def test_scaffolding_prepends_to_context(self, tmp_path: Path) -> None:
        """Scaffolding paths come before --context files in the prompt.

        Requirement 4.3: scaffolding injected BEFORE project-specific context.
        Uses --dry-run to inspect the prompt order.
        """
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        scaffold_marker = "SCAFFOLD_CONTENT_FIRST"
        _create_template(scaffolding_dir, "first-scaffold", ["code"],
                         body=f"# {scaffold_marker}\n" * 5)

        # Create a context file with a distinct marker
        context_file = tmp_path / "my_context.py"
        context_marker = "CONTEXT_CONTENT_SECOND"
        context_file.write_text(f"# {context_marker}\n" * 5, encoding="utf-8")

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding",
             "--tags", "code", "--context", str(context_file),
             "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        stdout = result.stdout
        # Both markers should be present
        assert scaffold_marker in stdout
        assert context_marker in stdout
        # Scaffolding should appear before the context file content
        scaffold_pos = stdout.index(scaffold_marker)
        context_pos = stdout.index(context_marker)
        assert scaffold_pos < context_pos, (
            f"Scaffolding (pos {scaffold_pos}) should appear before "
            f"context (pos {context_pos}) in prompt"
        )

    def test_scaffolding_uses_task_tags_for_selection(self, tmp_path: Path) -> None:
        """--scaffolding uses --tags for template matching (Requirement 6.2).

        Only templates matching the provided tags should be selected.
        """
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "test-scaffold", ["test", "property"],
                         body="# Test pattern\n" * 5)
        _create_template(scaffolding_dir, "api-scaffold", ["api", "rest"],
                         body="# API pattern\n" * 5)

        result = _run_local_coder(
            ["--task", "Write a property test", "--scaffolding",
             "--tags", "test", "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # test-scaffold matches, api-scaffold does not
        assert "test-scaffold" in result.stderr
        assert "api-scaffold" not in result.stderr

    def test_scaffolding_report_format(self, tmp_path: Path) -> None:
        """Stderr report line matches exact format (Requirement 6.5).

        Format: [SCAFFOLD] Selected N template(s): name1, name2, ...
        """
        scaffolding_dir = tmp_path / "scaffolding"
        scaffolding_dir.mkdir()
        _create_template(scaffolding_dir, "alpha", ["code"], priority=10,
                         body="# alpha\n" * 3)
        _create_template(scaffolding_dir, "beta", ["code"], priority=5,
                         body="# beta\n" * 3)

        result = _run_local_coder(
            ["--task", "Write code", "--scaffolding",
             "--tags", "code", "--dry-run"],
            env_overrides={"SCAFFOLDING_LIBRARY_PATH": str(scaffolding_dir)},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Find the scaffold report line
        scaffold_lines = [
            line for line in result.stderr.splitlines()
            if "[SCAFFOLD] Selected" in line
        ]
        assert len(scaffold_lines) == 1
        report = scaffold_lines[0]
        assert report.startswith("[SCAFFOLD] Selected 2 template(s):")
        assert "alpha" in report
        assert "beta" in report
