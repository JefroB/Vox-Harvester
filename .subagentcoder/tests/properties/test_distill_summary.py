# Feature: skill-distillation, Property 13: Summary comment present and accurate
"""Property-based tests for the summary comment in distilled output.

**Validates: Requirements 6.4**

For any non-empty Distilled_Prompt, the output SHALL end with an HTML comment in
the format `<!-- distilled: {N} tokens from {M} skills, {P}% reduction -->`
where N equals the estimated token count of the prompt, M equals the count of
included skill files, and P equals the integer-rounded percentage reduction from
full verbatim injection.
"""

import re
import sys
import tempfile
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import distill, DistillConfig, estimate_tokens


# --- Strategies ---

# Vocabulary for generating skill file content that will score against tasks
VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
    "cache", "async", "deploy", "testing", "build",
    "route", "middleware", "schema", "model", "endpoint",
    "logger", "metrics", "timeout", "retry", "connection",
]

SKILL_NAMES = [
    "Python Best Practices", "Security Guidelines", "API Design",
    "Testing Strategy", "Error Handling", "Performance Tuning",
]

# Regex for parsing the summary comment
SUMMARY_COMMENT_RE = re.compile(
    r"^<!-- distilled: (\d+) tokens from (\d+) skills?, (\d+)% reduction -->$"
)


@st.composite
def skill_file_content(draw, name=None, tag="code"):
    """Generate a skill file with frontmatter and sections containing extractable rules."""
    if name is None:
        name = draw(st.sampled_from(SKILL_NAMES))

    num_sections = draw(st.integers(min_value=2, max_value=4))
    sections_text = []

    for _ in range(num_sections):
        heading_words = draw(st.lists(st.sampled_from(VOCAB), min_size=2, max_size=4))
        heading = " ".join(heading_words)

        # Generate bullet-point rules (extractable content)
        num_rules = draw(st.integers(min_value=3, max_value=12))
        rules = []
        for _ in range(num_rules):
            rule_words = draw(st.lists(st.sampled_from(VOCAB), min_size=4, max_size=10))
            rules.append(f"- {' '.join(rule_words)}")

        body = "\n".join(rules)
        sections_text.append(f"## {heading}\n\n{body}")

    content = "\n\n".join(sections_text)
    file_text = f"---\nname: {name}\ntags: [{tag}]\n---\n\n{content}"
    return file_text


@st.composite
def multiple_skill_files(draw, min_files=1, max_files=4):
    """Generate multiple distinct skill files."""
    num_files = draw(st.integers(min_value=min_files, max_value=max_files))
    # Use unique names to get distinct skills in output
    names = draw(st.lists(
        st.sampled_from(SKILL_NAMES),
        min_size=num_files,
        max_size=num_files,
        unique=True,
    ))
    files = []
    for name in names:
        content = draw(skill_file_content(name=name))
        files.append(content)
    return files


@st.composite
def task_description_strategy(draw):
    """Generate task descriptions using vocabulary words to ensure scoring overlap."""
    words = draw(st.lists(st.sampled_from(VOCAB), min_size=3, max_size=8))
    return " ".join(words)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    skill_files=multiple_skill_files(min_files=1, max_files=4),
    task_desc=task_description_strategy(),
    budget=st.integers(min_value=500, max_value=16000),
)
def test_summary_comment_present_and_format(skill_files, task_desc, budget):
    """For any non-empty distilled output, it SHALL end with a summary comment
    matching the format: <!-- distilled: {N} tokens from {M} skills, {P}% reduction -->
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths = []
        for i, content in enumerate(skill_files):
            p = tmp / f"skill_{i}.md"
            p.write_text(content, encoding="utf-8")
            paths.append(p)

        config = DistillConfig(token_budget=budget, threshold=0.1)
        result = distill(task_desc, paths, config)

        # Only check non-empty prompts
        assume(result.prompt.strip() != "")

        # The output must end with the summary comment line
        lines = result.prompt.rstrip("\n").split("\n")
        last_line = lines[-1].strip()

        match = SUMMARY_COMMENT_RE.match(last_line)
        assert match is not None, (
            f"Summary comment not found or malformed at end of output.\n"
            f"Last line: {last_line!r}\n"
            f"Expected format: <!-- distilled: {{N}} tokens from {{M}} skills, {{P}}% reduction -->"
        )


@settings(max_examples=100)
@given(
    skill_files=multiple_skill_files(min_files=1, max_files=4),
    task_desc=task_description_strategy(),
    budget=st.integers(min_value=500, max_value=16000),
)
def test_summary_comment_m_matches_skills_included(skill_files, task_desc, budget):
    """M in the summary comment equals the number of skill files that appear
    as `### SKILL_NAME` headings in the output.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths = []
        for i, content in enumerate(skill_files):
            p = tmp / f"skill_{i}.md"
            p.write_text(content, encoding="utf-8")
            paths.append(p)

        config = DistillConfig(token_budget=budget, threshold=0.1)
        result = distill(task_desc, paths, config)

        assume(result.prompt.strip() != "")

        # Parse M from the summary comment
        lines = result.prompt.rstrip("\n").split("\n")
        last_line = lines[-1].strip()
        match = SUMMARY_COMMENT_RE.match(last_line)
        assume(match is not None)

        m_from_comment = int(match.group(2))

        # Count ### SKILL_NAME headings in the output
        heading_pattern = re.compile(r"^### (.+)$", re.MULTILINE)
        headings = heading_pattern.findall(result.prompt)
        actual_skill_count = len(headings)

        assert m_from_comment == actual_skill_count, (
            f"M in summary comment ({m_from_comment}) != "
            f"actual skill heading count ({actual_skill_count}).\n"
            f"Headings found: {headings}\n"
            f"result.skills_included: {result.skills_included}"
        )


@settings(max_examples=100)
@given(
    skill_files=multiple_skill_files(min_files=1, max_files=4),
    task_desc=task_description_strategy(),
    budget=st.integers(min_value=500, max_value=16000),
)
def test_summary_comment_m_matches_result_skills_included(skill_files, task_desc, budget):
    """M in the summary comment equals result.skills_included."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths = []
        for i, content in enumerate(skill_files):
            p = tmp / f"skill_{i}.md"
            p.write_text(content, encoding="utf-8")
            paths.append(p)

        config = DistillConfig(token_budget=budget, threshold=0.1)
        result = distill(task_desc, paths, config)

        assume(result.prompt.strip() != "")

        # Parse M from the summary comment
        lines = result.prompt.rstrip("\n").split("\n")
        last_line = lines[-1].strip()
        match = SUMMARY_COMMENT_RE.match(last_line)
        assume(match is not None)

        m_from_comment = int(match.group(2))

        assert m_from_comment == result.skills_included, (
            f"M in summary comment ({m_from_comment}) != "
            f"result.skills_included ({result.skills_included})"
        )


@settings(max_examples=100)
@given(
    skill_files=multiple_skill_files(min_files=1, max_files=4),
    task_desc=task_description_strategy(),
    budget=st.integers(min_value=500, max_value=16000),
)
def test_summary_comment_p_reduction_correct(skill_files, task_desc, budget):
    """P in the summary comment equals the integer-rounded percentage reduction
    from full verbatim injection: round(((tokens_full - N) / tokens_full) * 100).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths = []
        for i, content in enumerate(skill_files):
            p = tmp / f"skill_{i}.md"
            p.write_text(content, encoding="utf-8")
            paths.append(p)

        config = DistillConfig(token_budget=budget, threshold=0.1)
        result = distill(task_desc, paths, config)

        assume(result.prompt.strip() != "")
        assume(result.tokens_full > 0)

        # Parse N and P from the summary comment
        lines = result.prompt.rstrip("\n").split("\n")
        last_line = lines[-1].strip()
        match = SUMMARY_COMMENT_RE.match(last_line)
        assume(match is not None)

        n_from_comment = int(match.group(1))
        p_from_comment = int(match.group(3))

        # Expected P: round(((tokens_full - N) / tokens_full) * 100)
        expected_p = round(((result.tokens_full - n_from_comment) / result.tokens_full) * 100)

        assert p_from_comment == expected_p, (
            f"P in summary comment ({p_from_comment}%) != "
            f"expected ({expected_p}%).\n"
            f"N={n_from_comment}, tokens_full={result.tokens_full}\n"
            f"Formula: round((({result.tokens_full} - {n_from_comment}) / {result.tokens_full}) * 100)"
        )


@settings(max_examples=100)
@given(
    skill_files=multiple_skill_files(min_files=1, max_files=4),
    task_desc=task_description_strategy(),
    budget=st.integers(min_value=500, max_value=16000),
)
def test_summary_comment_ends_output(skill_files, task_desc, budget):
    """The summary comment is the last non-empty line in the output —
    nothing follows it.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths = []
        for i, content in enumerate(skill_files):
            p = tmp / f"skill_{i}.md"
            p.write_text(content, encoding="utf-8")
            paths.append(p)

        config = DistillConfig(token_budget=budget, threshold=0.1)
        result = distill(task_desc, paths, config)

        assume(result.prompt.strip() != "")

        # Find the last non-empty line
        lines = result.prompt.split("\n")
        non_empty_lines = [l for l in lines if l.strip()]
        assume(len(non_empty_lines) > 0)

        last_non_empty = non_empty_lines[-1].strip()

        assert SUMMARY_COMMENT_RE.match(last_non_empty), (
            f"The last non-empty line is not the summary comment.\n"
            f"Last non-empty line: {last_non_empty!r}\n"
            f"Full output (last 5 lines): {lines[-5:]}"
        )
