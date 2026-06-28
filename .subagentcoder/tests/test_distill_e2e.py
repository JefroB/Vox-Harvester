"""End-to-end integration tests for skill distillation via local_coder.py.

Tests the full --distill --dry-run path using subprocess (with a bootstrap
script to redirect SKILLS_DIR to fixtures), and also tests the distill()
function directly with fixture skill files.

Requirements: 8.1, 8.2, 6.1
"""

import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = WORKSPACE_ROOT / ".kiro" / "scripts"
LOCAL_CODER_SCRIPT = SCRIPTS_DIR / "local_coder.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"

# Add scripts dir to path for direct imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(WORKSPACE_ROOT))


class TestDistillDirect:
    """Test distill() function directly with fixture skill files."""

    def _get_fixture_paths(self):
        """Return list of all fixture skill file paths."""
        return sorted(FIXTURES_DIR.glob("*.md"))

    def test_distilled_output_smaller_than_verbatim(self):
        """Distilled output uses fewer tokens than full verbatim injection.

        Validates: Requirements 8.1, 6.1
        """
        from distiller import distill, DistillConfig, estimate_tokens

        skill_paths = self._get_fixture_paths()

        # Compute full verbatim token cost
        full_text = ""
        for path in skill_paths:
            full_text += path.read_text(encoding="utf-8")
        tokens_full = estimate_tokens(full_text)

        # Distill with a budget smaller than full content
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        assert result.tokens_used < result.tokens_full, (
            f"Distilled ({result.tokens_used}) should be smaller than "
            f"full verbatim ({result.tokens_full})"
        )

    def test_output_starts_with_skills_header(self):
        """Distilled prompt starts with the required header.

        Validates: Requirements 6.1
        """
        from distiller import distill, DistillConfig

        skill_paths = self._get_fixture_paths()
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        assert result.prompt.startswith("## SKILLS (Distilled for this task)")

    def test_output_ends_with_distilled_comment(self):
        """Distilled prompt ends with the summary HTML comment.

        Validates: Requirements 6.1
        """
        from distiller import distill, DistillConfig

        skill_paths = self._get_fixture_paths()
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        assert result.prompt.strip().endswith("-->")
        assert "<!-- distilled:" in result.prompt

    def test_at_least_one_skill_heading_in_output(self):
        """At least one ### SKILL_NAME heading appears in the output.

        Validates: Requirements 6.1
        """
        from distiller import distill, DistillConfig

        skill_paths = self._get_fixture_paths()
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        # Should have at least one ### heading
        headings = re.findall(r"^### .+$", result.prompt, re.MULTILINE)
        assert len(headings) >= 1, "Expected at least one ### SKILL_NAME heading"
        assert result.skills_included >= 1

    def test_always_tagged_skill_included(self):
        """The always-tagged skill (Software Engineering) appears in output.

        Validates: Requirements 8.1
        """
        from distiller import distill, DistillConfig

        skill_paths = self._get_fixture_paths()
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        # The always_tagged.md fixture has name "Software Engineering"
        assert "### SOFTWARE ENGINEERING" in result.prompt

    def test_api_related_content_included(self):
        """Content from API-related sections appears since task mentions API.

        Validates: Requirements 8.1
        """
        from distiller import distill, DistillConfig

        skill_paths = self._get_fixture_paths()
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        # The multi_section.md fixture has "API Design" as its name and
        # contains sections on Pagination and Authentication
        assert "### API DESIGN" in result.prompt

    def test_summary_comment_format(self):
        """Summary comment matches required format with tokens, skills, reduction.

        Validates: Requirements 6.1
        """
        from distiller import distill, DistillConfig

        skill_paths = self._get_fixture_paths()
        result = distill(
            task_description="Build a REST API with pagination and authentication",
            skill_paths=skill_paths,
            config=DistillConfig(token_budget=4000, threshold=0.1),
        )

        # Match the comment format: <!-- distilled: N tokens from M skills, P% reduction -->
        pattern = r"<!-- distilled: \d+ tokens from \d+ skills, \d+% reduction -->"
        assert re.search(pattern, result.prompt), (
            f"Summary comment not found in expected format. Output ends with:\n"
            f"{result.prompt[-200:]}"
        )


class TestDistillSubprocess:
    """Test distillation via subprocess, running local_coder.py with --distill --dry-run."""

    def _build_bootstrap_script(self, task, threshold=0.1, budget=4000):
        """Build a bootstrap script that patches SKILLS_DIR and runs local_coder dry-run."""
        # Use forward slashes to avoid Windows backslash escape issues
        scripts_dir_str = str(SCRIPTS_DIR).replace("\\", "/")
        workspace_str = str(WORKSPACE_ROOT).replace("\\", "/")
        fixtures_str = str(FIXTURES_DIR).replace("\\", "/")
        script_str = str(LOCAL_CODER_SCRIPT).replace("\\", "/")

        return textwrap.dedent(f"""\
import sys
import os
from pathlib import Path

# Set up paths
scripts_dir = "{scripts_dir_str}"
workspace_root = "{workspace_str}"
fixtures_dir = "{fixtures_str}"
script_path = "{script_str}"

sys.path.insert(0, scripts_dir)
sys.path.insert(0, workspace_root)
os.chdir(workspace_root)

# Read the local_coder script
with open(script_path, "r", encoding="utf-8") as f:
    code = f.read()

# Replace the SKILLS_DIR assignment to point at fixtures
patched_code = code.replace(
    'SKILLS_DIR = Path(__file__).parent.parent / "skills"',
    'SKILLS_DIR = Path("{fixtures_str}")',
)

# Set sys.argv for the CLI
sys.argv = [
    "local_coder.py",
    "--task", {repr(task)},
    "--distill",
    "--dry-run",
    "--distill-threshold", "{threshold}",
    "--token-budget", "{budget}",
    "--all-skills",
]

exec(compile(patched_code, script_path, "exec"), {{"__name__": "__main__", "__file__": script_path}})
""")

    def _run_bootstrap(self, task, threshold=0.1, budget=4000):
        """Run the bootstrap script and return (stdout, stderr, returncode)."""
        script_content = self._build_bootstrap_script(task, threshold, budget)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script_content)
            bootstrap_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, bootstrap_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(WORKSPACE_ROOT),
            )
            return result.stdout, result.stderr, result.returncode
        finally:
            Path(bootstrap_path).unlink(missing_ok=True)

    def test_dry_run_distill_prints_to_stdout(self):
        """--distill --dry-run prints distilled prompt to stdout.

        Validates: Requirements 8.1
        """
        stdout, stderr, rc = self._run_bootstrap(
            "Build a REST API with pagination and authentication"
        )

        assert rc == 0, f"Process exited with {rc}. stderr:\n{stderr}"
        assert "## SKILLS (Distilled for this task)" in stdout
        assert "<!-- distilled:" in stdout

    def test_dry_run_distill_diagnostics_on_stderr(self):
        """--distill --dry-run prints diagnostics to stderr.

        Validates: Requirements 8.2
        """
        stdout, stderr, rc = self._run_bootstrap(
            "Build a REST API with pagination and authentication"
        )

        assert rc == 0, f"Process exited with {rc}. stderr:\n{stderr}"
        # Should contain DISTILL-DIAG messages
        assert "[DISTILL-DIAG] Skill:" in stderr
        assert "[DISTILL-DIAG] Summary:" in stderr

    def test_diagnostic_shows_section_scores(self):
        """Diagnostics show section heading, INCLUDED/EXCLUDED status, and score.

        Validates: Requirements 8.2
        """
        stdout, stderr, rc = self._run_bootstrap(
            "Build a REST API with pagination and authentication"
        )

        assert rc == 0, f"Process exited with {rc}. stderr:\n{stderr}"
        # Should have score and token info for each section
        # Format: [DISTILL-DIAG]   Heading — STATUS (score: X.XX, ~N tokens)
        pattern = r"\[DISTILL-DIAG\]\s+.+ — (INCLUDED|EXCLUDED) \(score: \d+\.\d{2}, ~\d+ tokens\)"
        matches = re.findall(pattern, stderr)
        assert len(matches) >= 1, (
            f"Expected section diagnostics in stderr. Got:\n{stderr}"
        )

    def test_diagnostic_summary_line(self):
        """Diagnostics include summary with total tokens, sections, and threshold.

        Validates: Requirements 8.2
        """
        stdout, stderr, rc = self._run_bootstrap(
            "Build a REST API with pagination and authentication"
        )

        assert rc == 0, f"Process exited with {rc}. stderr:\n{stderr}"
        # Format: [DISTILL-DIAG] Summary: N tokens, X/Y sections, threshold=Z
        pattern = r"\[DISTILL-DIAG\] Summary: \d+ tokens, \d+/\d+ sections, threshold=[\d.]+"
        assert re.search(pattern, stderr), (
            f"Summary line not found in stderr. Got:\n{stderr}"
        )

    def test_distilled_stdout_is_smaller_than_full_skill_content(self):
        """The distilled output on stdout is smaller than verbatim skill injection.

        Validates: Requirements 8.1
        """
        from distiller import estimate_tokens

        stdout, stderr, rc = self._run_bootstrap(
            "Build a REST API with pagination and authentication",
            budget=2000,
        )

        assert rc == 0, f"Process exited with {rc}. stderr:\n{stderr}"

        # Compute full verbatim cost from fixtures
        full_text = ""
        for path in sorted(FIXTURES_DIR.glob("*.md")):
            full_text += path.read_text(encoding="utf-8")
        tokens_full = estimate_tokens(full_text)

        # The stdout should be the distilled prompt, which should be smaller
        tokens_distilled = estimate_tokens(stdout)
        assert tokens_distilled < tokens_full, (
            f"Distilled output ({tokens_distilled} tokens) should be smaller than "
            f"full verbatim ({tokens_full} tokens)"
        )

    def test_distill_token_info_on_stderr(self):
        """Token usage info appears on stderr during distillation.

        Validates: Requirements 8.2
        """
        stdout, stderr, rc = self._run_bootstrap(
            "Build a REST API with pagination and authentication"
        )

        assert rc == 0, f"Process exited with {rc}. stderr:\n{stderr}"
        # The distiller reports token usage: [DISTILL] N/budget tokens used (P%)
        assert "[DISTILL]" in stderr
