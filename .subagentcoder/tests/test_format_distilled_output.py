"""Unit tests for format_distilled_output function.

Tests Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 2.4, 2.5
"""

import sys
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".kiro" / "scripts"))

from distiller import (
    format_distilled_output,
    estimate_tokens,
    assemble_prompt,
    ScoredSection,
    Section,
    CodeBlock,
    DistillConfig,
)


class TestFormatDistilledOutputHeader:
    """Test that output starts with the correct header."""

    def test_header_present(self):
        body = "### SOFTWARE ENGINEERING\n- Rule one\n- Rule two"
        result = format_distilled_output(body, tokens_full=1000, skills_count=1, had_task_specific_matches=True)
        assert result.startswith("## SKILLS (Distilled for this task)\n\n")

    def test_header_followed_by_body(self):
        body = "### SECURITY\n- Never trust user input"
        result = format_distilled_output(body, tokens_full=500, skills_count=1, had_task_specific_matches=True)
        lines = result.split("\n")
        assert lines[0] == "## SKILLS (Distilled for this task)"
        assert lines[1] == ""
        assert lines[2] == "### SECURITY"


class TestFormatDistilledOutputSummaryComment:
    """Test the summary HTML comment format."""

    def test_comment_at_end(self):
        body = "### CODING\n- Write clean code"
        result = format_distilled_output(body, tokens_full=1000, skills_count=1, had_task_specific_matches=True)
        # Last line should be the HTML comment
        last_line = result.strip().split("\n")[-1]
        assert last_line.startswith("<!-- distilled:")
        assert "tokens from 1 skills" in last_line
        assert "% reduction -->" in last_line

    def test_comment_format(self):
        body = "### TESTING\n- Test all edge cases\n- Use mocks sparingly"
        result = format_distilled_output(body, tokens_full=2000, skills_count=3, had_task_specific_matches=True)
        last_line = result.strip().split("\n")[-1]
        # Verify format: <!-- distilled: {N} tokens from {M} skills, {P}% reduction -->
        assert "tokens from 3 skills" in last_line
        assert last_line.startswith("<!-- distilled: ")
        assert last_line.endswith(" -->")

    def test_token_count_in_comment_is_accurate(self):
        body = "### API\n- Use REST conventions\n- Return proper status codes"
        result = format_distilled_output(body, tokens_full=5000, skills_count=1, had_task_specific_matches=True)
        # The N in the comment should match estimate_tokens of the full output
        actual_tokens = estimate_tokens(result)
        last_line = result.strip().split("\n")[-1]
        # Extract N from <!-- distilled: {N} tokens ...
        n_str = last_line.split("distilled: ")[1].split(" tokens")[0]
        n = int(n_str)
        assert n == actual_tokens

    def test_reduction_percentage(self):
        body = "### CODE\n- Keep it simple"
        tokens_full = 1000
        result = format_distilled_output(body, tokens_full=tokens_full, skills_count=1, had_task_specific_matches=True)
        actual_tokens = estimate_tokens(result)
        expected_pct = round(((tokens_full - actual_tokens) / tokens_full) * 100)
        last_line = result.strip().split("\n")[-1]
        assert f"{expected_pct}% reduction" in last_line

    def test_zero_tokens_full(self):
        body = "### CODE\n- Rule"
        result = format_distilled_output(body, tokens_full=0, skills_count=1, had_task_specific_matches=True)
        last_line = result.strip().split("\n")[-1]
        assert "0% reduction" in last_line


class TestFormatDistilledOutputNoMatch:
    """Test the no-match note behavior."""

    def test_no_match_note_when_no_task_specific(self):
        body = "### SOFTWARE ENGINEERING\n- Always write tests"
        result = format_distilled_output(body, tokens_full=1000, skills_count=1, had_task_specific_matches=False)
        assert "<!-- no task-specific skills matched threshold -->" in result

    def test_no_match_note_absent_when_matches_exist(self):
        body = "### SOFTWARE ENGINEERING\n- Always write tests"
        result = format_distilled_output(body, tokens_full=1000, skills_count=1, had_task_specific_matches=True)
        assert "<!-- no task-specific skills matched threshold -->" not in result

    def test_no_match_note_before_summary_comment(self):
        body = "### ENGINEERING\n- Rule"
        result = format_distilled_output(body, tokens_full=1000, skills_count=1, had_task_specific_matches=False)
        lines = result.strip().split("\n")
        # Find both comments
        no_match_idx = None
        summary_idx = None
        for i, line in enumerate(lines):
            if "no task-specific skills matched" in line:
                no_match_idx = i
            if line.startswith("<!-- distilled:"):
                summary_idx = i
        assert no_match_idx is not None
        assert summary_idx is not None
        assert no_match_idx < summary_idx


class TestFormatDistilledOutputEmpty:
    """Test empty input handling."""

    def test_empty_body_returns_empty(self):
        result = format_distilled_output("", tokens_full=1000, skills_count=0, had_task_specific_matches=True)
        assert result == ""

    def test_whitespace_only_body_returns_empty(self):
        result = format_distilled_output("   \n  \n  ", tokens_full=1000, skills_count=0, had_task_specific_matches=True)
        assert result == ""


class TestAssemblePromptSkillOrdering:
    """Test that skill blocks in assemble_prompt are ordered by highest section score descending."""

    def test_skills_ordered_by_max_score(self):
        """Skill with highest max section score should appear first."""
        sections = [
            ScoredSection(
                section=Section(heading="Auth", body="- Validate tokens", code_blocks=[], is_preamble=False),
                skill_name="Security",
                raw_score=0.9,
                normalized_score=1.0,
            ),
            ScoredSection(
                section=Section(heading="Patterns", body="- Use factories", code_blocks=[], is_preamble=False),
                skill_name="Design",
                raw_score=0.5,
                normalized_score=0.6,
            ),
            ScoredSection(
                section=Section(heading="Testing", body="- Write unit tests", code_blocks=[], is_preamble=False),
                skill_name="Testing",
                raw_score=0.7,
                normalized_score=0.8,
            ),
        ]
        config = DistillConfig(token_budget=4000)
        result, _ = assemble_prompt(sections, config, always_sections=[])
        lines = result.split("\n")

        # Find skill headings in order
        headings = [l for l in lines if l.startswith("### ")]
        assert headings[0] == "### SECURITY"
        assert headings[1] == "### TESTING"
        assert headings[2] == "### DESIGN"

    def test_sections_within_skill_ordered_by_score(self):
        """Within a skill block, sections should appear by descending score."""
        sections = [
            ScoredSection(
                section=Section(heading="Low", body="- Low priority rule", code_blocks=[], is_preamble=False),
                skill_name="Skill A",
                raw_score=0.3,
                normalized_score=0.5,
            ),
            ScoredSection(
                section=Section(heading="High", body="- High priority rule", code_blocks=[], is_preamble=False),
                skill_name="Skill A",
                raw_score=0.6,
                normalized_score=1.0,
            ),
        ]
        config = DistillConfig(token_budget=4000)
        result, _ = assemble_prompt(sections, config, always_sections=[])

        # "High priority rule" should come before "Low priority rule"
        high_idx = result.index("High priority rule")
        low_idx = result.index("Low priority rule")
        assert high_idx < low_idx

    def test_code_blocks_preserved_with_language(self):
        """Code blocks should have language annotation preserved."""
        cb = CodeBlock(language="python", content="def hello():\n    pass", preceding_text="- Example function")
        sections = [
            ScoredSection(
                section=Section(
                    heading="Examples",
                    body="- Example function\n\n```python\ndef hello():\n    pass\n```",
                    code_blocks=[cb],
                    is_preamble=False,
                ),
                skill_name="Coding",
                raw_score=0.8,
                normalized_score=1.0,
            ),
        ]
        config = DistillConfig(token_budget=4000)
        result, _ = assemble_prompt(sections, config, always_sections=[])
        assert "```python" in result
        assert "def hello():" in result
        assert "```" in result
