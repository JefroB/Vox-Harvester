"""Unit tests for scaffolding selector module.

Validates: Requirements 2.1, 2.5, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 5.2
"""

from pathlib import Path

from local_coder.scaffolding_selector import (
    TemplateInfo,
    _apply_budget,
    _apply_overrides,
    _filter_by_complexity,
    _parse_template_frontmatter,
    _rank_candidates,
)


class TestParseTemplateFrontmatter:
    """Tests for _parse_template_frontmatter function."""

    def test_valid_frontmatter_all_fields(self, tmp_path: Path) -> None:
        """Complete valid frontmatter with all fields parses correctly."""
        template = tmp_path / "template.md"
        template.write_text(
            "---\n"
            "name: my-template\n"
            "tags: [code, test, python]\n"
            "category: test-skeleton\n"
            "complexity: complex\n"
            "description: A test skeleton for property-based tests\n"
            "priority: 10\n"
            "---\n"
            "Body content here\n",
            encoding="utf-8",
        )

        result = _parse_template_frontmatter(template)

        assert result is not None
        assert result["name"] == "my-template"
        assert result["tags"] == ["code", "test", "python"]
        assert result["category"] == "test-skeleton"
        assert result["complexity"] == "complex"
        assert result["description"] == "A test skeleton for property-based tests"
        assert result["priority"] == 10

    def test_partial_frontmatter_defaults(self, tmp_path: Path) -> None:
        """Frontmatter missing complexity and priority gets defaults."""
        template = tmp_path / "partial.md"
        template.write_text(
            "---\n"
            "name: partial-template\n"
            "tags: [code]\n"
            "category: helper\n"
            "description: A helper template\n"
            "---\n",
            encoding="utf-8",
        )

        result = _parse_template_frontmatter(template)

        assert result is not None
        assert result["name"] == "partial-template"
        assert result["tags"] == ["code"]
        assert result["category"] == "helper"
        assert result["description"] == "A helper template"
        assert result["complexity"] == "any"
        assert result["priority"] == 0

    def test_missing_frontmatter_returns_none(self, tmp_path: Path) -> None:
        """File with no --- delimiters returns None."""
        template = tmp_path / "no_frontmatter.md"
        template.write_text(
            "This is just plain text.\n"
            "No frontmatter here at all.\n",
            encoding="utf-8",
        )

        result = _parse_template_frontmatter(template)

        assert result is None

    def test_malformed_yaml_emits_warning(
        self, tmp_path: Path, capsys
    ) -> None:
        """Malformed YAML between --- delimiters emits warning to stderr."""
        template = tmp_path / "malformed.md"
        template.write_text(
            "---\n"
            "name: [unclosed\n"
            "---\n",
            encoding="utf-8",
        )

        result = _parse_template_frontmatter(template)
        captured = capsys.readouterr()

        assert result is None
        assert str(template) in captured.err
        assert "[SCAFFOLD WARN]" in captured.err

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        """Empty file returns None (no frontmatter present)."""
        template = tmp_path / "empty.md"
        template.write_text("", encoding="utf-8")

        result = _parse_template_frontmatter(template)

        assert result is None

    def test_frontmatter_with_body_text(self, tmp_path: Path) -> None:
        """Valid frontmatter followed by body text parses correctly; body is ignored."""
        template = tmp_path / "with_body.py"
        template.write_text(
            "---\n"
            "name: retry-pattern\n"
            "tags: [code, resilience]\n"
            "category: code-template\n"
            "complexity: simple\n"
            "description: Retry with exponential backoff\n"
            "priority: 5\n"
            "---\n"
            "import time\n"
            "\n"
            "def retry(fn, max_attempts=3):\n"
            "    for i in range(max_attempts):\n"
            "        try:\n"
            "            return fn()\n"
            "        except Exception:\n"
            "            time.sleep(2 ** i)\n",
            encoding="utf-8",
        )

        result = _parse_template_frontmatter(template)

        assert result is not None
        assert result["name"] == "retry-pattern"
        assert result["tags"] == ["code", "resilience"]
        assert result["category"] == "code-template"
        assert result["complexity"] == "simple"
        assert result["description"] == "Retry with exponential backoff"
        assert result["priority"] == 5


# --- Helper to build TemplateInfo objects concisely ---

def _make_template(
    name: str,
    tags: list[str] | None = None,
    priority: int = 0,
    complexity: str = "any",
    source: str = "shared",
    token_estimate: int = 100,
) -> TemplateInfo:
    """Create a TemplateInfo with sensible defaults for testing."""
    return TemplateInfo(
        name=name,
        path=Path(f"/fake/{name}.md"),
        tags=tags or ["test"],
        category="test",
        complexity=complexity,
        description=f"Description for {name}",
        priority=priority,
        source=source,
        token_estimate=token_estimate,
    )


class TestApplyOverrides:
    """Tests for _apply_overrides — Validates: Requirements 5.2, 5.3, 5.4."""

    def test_overlapping_names_project_wins(self) -> None:
        """When shared and project have same-named template, project version is kept."""
        shared = [
            _make_template("A", source="shared"),
            _make_template("B", source="shared"),
        ]
        project = [
            _make_template("B", source="project"),
            _make_template("C", source="project"),
        ]

        result = _apply_overrides(shared, project)

        result_names = [t.name for t in result]
        assert sorted(result_names) == ["A", "B", "C"]
        # B should come from project, not shared
        b_template = next(t for t in result if t.name == "B")
        assert b_template.source == "project"
        # A should remain from shared
        a_template = next(t for t in result if t.name == "A")
        assert a_template.source == "shared"

    def test_unique_names_all_included(self) -> None:
        """When no overlapping names, all templates from both sources are included."""
        shared = [
            _make_template("A", source="shared"),
            _make_template("B", source="shared"),
        ]
        project = [
            _make_template("C", source="project"),
            _make_template("D", source="project"),
        ]

        result = _apply_overrides(shared, project)

        result_names = sorted(t.name for t in result)
        assert result_names == ["A", "B", "C", "D"]
        assert len(result) == 4

    def test_empty_shared_returns_only_project(self) -> None:
        """When shared is empty, only project templates are returned."""
        project = [_make_template("X", source="project")]

        result = _apply_overrides([], project)

        assert len(result) == 1
        assert result[0].name == "X"
        assert result[0].source == "project"

    def test_empty_project_returns_only_shared(self) -> None:
        """When project is empty, only shared templates are returned."""
        shared = [_make_template("Y", source="shared")]

        result = _apply_overrides(shared, [])

        assert len(result) == 1
        assert result[0].name == "Y"
        assert result[0].source == "shared"


class TestRankCandidates:
    """Tests for _rank_candidates — Validates: Requirements 3.1, 3.3, 3.5."""

    def test_sort_order_tag_overlap_priority_name(self) -> None:
        """Templates sorted by tag overlap desc, priority desc, name asc."""
        # Template with 2 tag overlaps, priority 5
        t_high_overlap = _make_template("beta", tags=["code", "test", "extra"], priority=5)
        # Template with 1 tag overlap, priority 10
        t_high_priority = _make_template("alpha", tags=["code", "unrelated"], priority=10)
        # Template with 1 tag overlap, priority 10, name later alphabetically
        t_high_priority_z = _make_template("zeta", tags=["test", "unrelated"], priority=10)

        candidates = [t_high_priority_z, t_high_overlap, t_high_priority]
        task_tags = ["code", "test"]

        result = _rank_candidates(candidates, task_tags)

        # beta has 2 overlaps (code, test) — should be first
        # alpha has 1 overlap (code), priority 10 — second (alpha < zeta)
        # zeta has 1 overlap (test), priority 10 — third
        assert result[0].name == "beta"
        assert result[1].name == "alpha"
        assert result[2].name == "zeta"

    def test_filters_disjoint_tags(self) -> None:
        """Templates with no overlapping tags are excluded from results."""
        t_match = _make_template("match", tags=["code", "test"])
        t_disjoint = _make_template("disjoint", tags=["unrelated", "other"])

        candidates = [t_match, t_disjoint]
        task_tags = ["code", "test"]

        result = _rank_candidates(candidates, task_tags)

        result_names = [t.name for t in result]
        assert "match" in result_names
        assert "disjoint" not in result_names

    def test_empty_task_tags_returns_empty(self) -> None:
        """When task_tags is empty, no template can overlap — returns empty list."""
        t1 = _make_template("a", tags=["code"])
        t2 = _make_template("b", tags=["test"])

        result = _rank_candidates([t1, t2], task_tags=[])

        assert result == []

    def test_all_candidates_disjoint_returns_empty(self) -> None:
        """When no candidate has overlapping tags, result is empty."""
        t1 = _make_template("x", tags=["unrelated"])
        t2 = _make_template("y", tags=["other"])

        result = _rank_candidates([t1, t2], task_tags=["code", "test"])

        assert result == []


class TestApplyBudget:
    """Tests for _apply_budget — Validates: Requirements 3.4, 3.6, 4.5."""

    def test_all_fit_within_budget(self) -> None:
        """When total tokens <= budget, all templates are included."""
        templates = [
            _make_template("a", token_estimate=100),
            _make_template("b", token_estimate=200),
            _make_template("c", token_estimate=300),
        ]

        result = _apply_budget(templates, budget_tokens=600)

        assert len(result) == 3
        assert [t.name for t in result] == ["a", "b", "c"]

    def test_exceeds_budget_stops_early(self) -> None:
        """When adding next template exceeds budget, stop (greedy break)."""
        templates = [
            _make_template("a", token_estimate=100),
            _make_template("b", token_estimate=200),
            _make_template("c", token_estimate=300),
        ]

        # Budget = 350: a(100) + b(200) = 300 <= 350, but +c(300) = 600 > 350
        result = _apply_budget(templates, budget_tokens=350)

        assert len(result) == 2
        assert [t.name for t in result] == ["a", "b"]

    def test_exact_budget_boundary(self) -> None:
        """When cumulative tokens exactly equal budget, all fit."""
        templates = [
            _make_template("a", token_estimate=100),
            _make_template("b", token_estimate=200),
        ]

        # Budget = 300: a(100) + b(200) = 300 == 300 — both fit
        result = _apply_budget(templates, budget_tokens=300)

        assert len(result) == 2
        assert [t.name for t in result] == ["a", "b"]

    def test_first_template_exceeds_budget(self) -> None:
        """When even the first template exceeds budget, return empty."""
        templates = [_make_template("big", token_estimate=500)]

        result = _apply_budget(templates, budget_tokens=100)

        assert result == []

    def test_empty_input_returns_empty(self) -> None:
        """Empty ranked list returns empty result regardless of budget."""
        result = _apply_budget([], budget_tokens=10000)

        assert result == []


class TestFilterByComplexity:
    """Tests for _filter_by_complexity — Validates: Requirements 3.2."""

    def test_simple_filter_keeps_simple_and_any(self) -> None:
        """Filtering with 'simple' keeps templates with complexity 'simple' or 'any'."""
        t_simple = _make_template("s", complexity="simple")
        t_complex = _make_template("c", complexity="complex")
        t_any = _make_template("a", complexity="any")

        result = _filter_by_complexity([t_simple, t_complex, t_any], "simple")

        result_names = sorted(t.name for t in result)
        assert result_names == ["a", "s"]

    def test_complex_filter_keeps_complex_and_any(self) -> None:
        """Filtering with 'complex' keeps templates with complexity 'complex' or 'any'."""
        t_simple = _make_template("s", complexity="simple")
        t_complex = _make_template("c", complexity="complex")
        t_any = _make_template("a", complexity="any")

        result = _filter_by_complexity([t_simple, t_complex, t_any], "complex")

        result_names = sorted(t.name for t in result)
        assert result_names == ["a", "c"]

    def test_any_filter_passes_all(self) -> None:
        """Filtering with 'any' returns all templates unchanged."""
        t_simple = _make_template("s", complexity="simple")
        t_complex = _make_template("c", complexity="complex")
        t_any = _make_template("a", complexity="any")

        result = _filter_by_complexity([t_simple, t_complex, t_any], "any")

        assert len(result) == 3
        result_names = sorted(t.name for t in result)
        assert result_names == ["a", "c", "s"]

    def test_empty_candidates_returns_empty(self) -> None:
        """Filtering empty list returns empty regardless of complexity."""
        result = _filter_by_complexity([], "simple")

        assert result == []


# --- Path Resolution and Discovery Tests ---
# Validates: Requirements 1.3, 9.1, 9.2, 9.3, 9.4

from unittest.mock import patch

from local_coder.scaffolding_selector import (
    _discover_templates,
    _resolve_project_path,
    _resolve_shared_path,
)


class TestResolveSharedPath:
    """Tests for _resolve_shared_path — Validates: Requirements 9.1, 9.2, 9.4."""

    def test_override_existing_dir_returns_it(self, tmp_path: Path) -> None:
        """When override is an existing directory, returns it directly."""
        override_dir = tmp_path / "custom-shared"
        override_dir.mkdir()

        result = _resolve_shared_path(override=override_dir)

        assert result == override_dir

    def test_override_nonexistent_dir_returns_none_or_fallback(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """When override points to non-existing dir, it's skipped (falls through)."""
        nonexistent = tmp_path / "does-not-exist"
        # Ensure no env var and no home fallback
        monkeypatch.delenv("SCAFFOLDING_LIBRARY_PATH", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")

        result = _resolve_shared_path(override=nonexistent)

        assert result is None

    def test_env_var_existing_dir(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """When SCAFFOLDING_LIBRARY_PATH env var points to existing dir, returns it."""
        env_dir = tmp_path / "env-scaffolding"
        env_dir.mkdir()
        monkeypatch.setenv("SCAFFOLDING_LIBRARY_PATH", str(env_dir))

        result = _resolve_shared_path()

        assert result == env_dir

    def test_env_var_nonexistent_falls_back_to_home(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """When env var path doesn't exist but ~/.kiro/scaffolding/ does, uses fallback."""
        # Set env var to nonexistent path
        monkeypatch.setenv("SCAFFOLDING_LIBRARY_PATH", str(tmp_path / "missing"))
        # Create the home fallback
        fake_home = tmp_path / "home"
        fallback_dir = fake_home / ".kiro" / "scaffolding"
        fallback_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        result = _resolve_shared_path()

        assert result == fallback_dir

    def test_env_var_nonexistent_no_fallback_returns_none(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """When env var path doesn't exist and no home fallback, returns None."""
        monkeypatch.setenv("SCAFFOLDING_LIBRARY_PATH", str(tmp_path / "missing"))
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        result = _resolve_shared_path()

        assert result is None

    def test_no_env_var_uses_home_fallback(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """When no env var set and ~/.kiro/scaffolding/ exists, returns it."""
        monkeypatch.delenv("SCAFFOLDING_LIBRARY_PATH", raising=False)
        fake_home = tmp_path / "home"
        fallback_dir = fake_home / ".kiro" / "scaffolding"
        fallback_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        result = _resolve_shared_path()

        assert result == fallback_dir

    def test_no_env_var_no_home_fallback_returns_none(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """When no env var and no ~/.kiro/scaffolding/, returns None."""
        monkeypatch.delenv("SCAFFOLDING_LIBRARY_PATH", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        result = _resolve_shared_path()

        assert result is None


class TestResolveProjectPath:
    """Tests for _resolve_project_path — Validates: Requirements 9.1, 5.1."""

    def test_override_existing_dir_returns_it(self, tmp_path: Path) -> None:
        """When override is an existing directory, returns it directly."""
        override_dir = tmp_path / "project-scaffolding"
        override_dir.mkdir()

        result = _resolve_project_path(override=override_dir)

        assert result == override_dir

    def test_override_nonexistent_checks_workspace(self, tmp_path: Path) -> None:
        """When override is non-existing, falls through to workspace check."""
        nonexistent = tmp_path / "nope"

        with patch(
            "local_coder.scaffolding_selector._WORKSPACE_ROOT", tmp_path
        ):
            result = _resolve_project_path(override=nonexistent)

        # No .kiro/scaffolding/ in tmp_path either
        assert result is None

    def test_workspace_kiro_scaffolding_exists(self, tmp_path: Path) -> None:
        """When .kiro/scaffolding/ exists relative to workspace root, returns it."""
        project_dir = tmp_path / ".kiro" / "scaffolding"
        project_dir.mkdir(parents=True)

        with patch(
            "local_coder.scaffolding_selector._WORKSPACE_ROOT", tmp_path
        ):
            result = _resolve_project_path()

        assert result == project_dir

    def test_workspace_kiro_scaffolding_missing(self, tmp_path: Path) -> None:
        """When .kiro/scaffolding/ doesn't exist in workspace, returns None."""
        with patch(
            "local_coder.scaffolding_selector._WORKSPACE_ROOT", tmp_path
        ):
            result = _resolve_project_path()

        assert result is None


class TestDiscoverTemplates:
    """Tests for _discover_templates — Validates: Requirements 1.3, 8.2, 10.4."""

    def _write_template(
        self, path: Path, name: str, tags: list[str], category: str = "test"
    ) -> None:
        """Helper to write a template file with valid frontmatter."""
        content = (
            "---\n"
            f"name: {name}\n"
            f"tags: [{', '.join(tags)}]\n"
            f"category: {category}\n"
            f"description: Template {name}\n"
            "priority: 5\n"
            "---\n"
            f"# Body for {name}\n"
            "Some content here.\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_discovers_valid_md_template(self, tmp_path: Path) -> None:
        """Discovers a .md file with valid frontmatter and builds TemplateInfo."""
        self._write_template(
            tmp_path / "test-patterns" / "skeleton.md",
            name="skeleton",
            tags=["test", "property"],
        )

        result = _discover_templates(tmp_path, "shared")

        assert len(result) == 1
        assert result[0].name == "skeleton"
        assert result[0].tags == ["test", "property"]
        assert result[0].source == "shared"
        assert result[0].token_estimate > 0

    def test_discovers_valid_py_template(self, tmp_path: Path) -> None:
        """Discovers a .py file with valid frontmatter."""
        self._write_template(
            tmp_path / "helpers" / "util.py",
            name="util-helper",
            tags=["code", "utility"],
        )

        result = _discover_templates(tmp_path, "project")

        assert len(result) == 1
        assert result[0].name == "util-helper"
        assert result[0].source == "project"

    def test_discovers_ts_and_js_templates(self, tmp_path: Path) -> None:
        """Discovers .ts and .js files with valid frontmatter."""
        self._write_template(
            tmp_path / "code" / "pattern.ts",
            name="ts-pattern",
            tags=["code"],
        )
        self._write_template(
            tmp_path / "code" / "helper.js",
            name="js-helper",
            tags=["code"],
        )

        result = _discover_templates(tmp_path, "shared")

        names = sorted(t.name for t in result)
        assert names == ["js-helper", "ts-pattern"]

    def test_filters_out_unsupported_extensions(self, tmp_path: Path) -> None:
        """Files with .txt, .json, .yaml extensions are ignored."""
        # Valid .md template
        self._write_template(
            tmp_path / "valid.md", name="valid", tags=["code"]
        )
        # Unsupported extensions — should be ignored
        for ext in [".txt", ".json", ".yaml", ".css", ".html"]:
            bad_file = tmp_path / f"ignored{ext}"
            bad_file.write_text(
                "---\nname: bad\ntags: [code]\ncategory: x\n"
                "description: bad\n---\nbody\n",
                encoding="utf-8",
            )

        result = _discover_templates(tmp_path, "shared")

        assert len(result) == 1
        assert result[0].name == "valid"

    def test_skips_files_without_frontmatter(self, tmp_path: Path) -> None:
        """Files without --- delimiters are skipped (no frontmatter)."""
        no_fm = tmp_path / "no-frontmatter.md"
        no_fm.write_text("Just plain text, no frontmatter.\n", encoding="utf-8")

        result = _discover_templates(tmp_path, "shared")

        assert result == []

    def test_skips_malformed_frontmatter(self, tmp_path: Path) -> None:
        """Files with malformed YAML frontmatter are skipped with warning."""
        malformed = tmp_path / "bad.md"
        malformed.write_text(
            "---\nname: [unclosed bracket\n---\nbody\n", encoding="utf-8"
        )

        result = _discover_templates(tmp_path, "shared")

        assert result == []

    def test_recursive_discovery_in_subdirectories(self, tmp_path: Path) -> None:
        """Discovers templates recursively in nested subdirectories."""
        self._write_template(
            tmp_path / "cat1" / "sub" / "deep.md",
            name="deep-template",
            tags=["deep"],
        )
        self._write_template(
            tmp_path / "cat2" / "shallow.py",
            name="shallow-template",
            tags=["shallow"],
        )

        result = _discover_templates(tmp_path, "shared")

        names = sorted(t.name for t in result)
        assert names == ["deep-template", "shallow-template"]

    def test_nonexistent_directory_returns_empty(self, tmp_path: Path) -> None:
        """When directory doesn't exist, returns empty list."""
        result = _discover_templates(tmp_path / "missing", "shared")

        assert result == []

    def test_mixed_valid_and_invalid_files(self, tmp_path: Path) -> None:
        """Correctly processes valid templates while skipping invalid ones."""
        # Valid template
        self._write_template(
            tmp_path / "good.md", name="good", tags=["test"]
        )
        # Invalid: no frontmatter
        (tmp_path / "plain.md").write_text("no frontmatter here", encoding="utf-8")
        # Invalid: unsupported extension
        (tmp_path / "ignored.txt").write_text(
            "---\nname: x\ntags: [y]\ncategory: z\n"
            "description: w\n---\nbody\n",
            encoding="utf-8",
        )
        # Invalid: malformed YAML
        (tmp_path / "broken.py").write_text(
            "---\nname: [bad\n---\nbody\n", encoding="utf-8"
        )

        result = _discover_templates(tmp_path, "shared")

        assert len(result) == 1
        assert result[0].name == "good"
