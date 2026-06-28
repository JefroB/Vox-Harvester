# Feature: skill-distillation, Property 12: Output formatting invariants
"""Property-based tests for output formatting.

**Validates: Requirements 6.2, 6.3, 2.5**

For any distilled output, every extracted rule SHALL be formatted as a markdown
bullet point (starting with `- `). Every included code example SHALL be wrapped
in a fenced code block with its original language annotation preserved. Each
skill block SHALL begin with `### SKILL_NAME` where SKILL_NAME is the uppercase
frontmatter name.
"""

import re
import sys
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import assemble_prompt, ScoredSection, Section, CodeBlock, DistillConfig


# --- Strategies ---

# Non-stop vocabulary for generating meaningful content
NON_STOP_VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
    "cache", "async", "deploy", "testing", "build",
    "route", "middleware", "schema", "model", "endpoint",
]

LANGUAGES = ["python", "javascript", "typescript", "bash", "rust", "go", "java"]

SKILL_NAMES = [
    "software-engineering", "security", "testing-strategy",
    "api-design", "performance", "error-handling",
]


@st.composite
def rule_lines(draw):
    """Generate a list of rule lines in various formats (bullets, numbered, imperative)."""
    # Bullets
    bullet_count = draw(st.integers(min_value=1, max_value=4))
    bullets = []
    for _ in range(bullet_count):
        words = draw(st.lists(st.sampled_from(NON_STOP_VOCAB), min_size=2, max_size=6))
        bullets.append("- " + " ".join(words))

    # Numbered items
    numbered_count = draw(st.integers(min_value=0, max_value=3))
    numbered = []
    for i in range(numbered_count):
        words = draw(st.lists(st.sampled_from(NON_STOP_VOCAB), min_size=2, max_size=6))
        numbered.append(f"{i + 1}. " + " ".join(words))

    # Imperative statements (verb-initial or containing SHALL/MUST)
    imp_count = draw(st.integers(min_value=0, max_value=2))
    imperatives = []
    for _ in range(imp_count):
        words = draw(st.lists(st.sampled_from(NON_STOP_VOCAB), min_size=2, max_size=5))
        keyword = draw(st.sampled_from(["SHALL", "MUST", "NEVER", "ALWAYS"]))
        imperatives.append(" ".join(words[:2]) + f" {keyword} " + " ".join(words[2:]))

    return bullets + numbered + imperatives


@st.composite
def code_blocks_strategy(draw):
    """Generate a list of CodeBlocks with known languages."""
    count = draw(st.integers(min_value=0, max_value=3))
    blocks = []
    for _ in range(count):
        lang = draw(st.sampled_from(LANGUAGES))
        content_lines = draw(st.lists(
            st.lists(st.sampled_from(NON_STOP_VOCAB), min_size=1, max_size=4).map(
                lambda w: " ".join(w)
            ),
            min_size=1,
            max_size=4,
        ))
        content = "\n".join(content_lines)
        preceding = draw(st.lists(
            st.sampled_from(NON_STOP_VOCAB), min_size=1, max_size=3
        ).map(lambda w: " ".join(w)))
        blocks.append(CodeBlock(language=lang, content=content, preceding_text=preceding))
    return blocks


@st.composite
def scored_sections_for_formatting(draw):
    """Generate a list of ScoredSections with known skill names, rules, and code blocks.

    Returns (scored_sections, skill_names_used, code_blocks_used) for verification.
    """
    # Pick 1-3 skills
    num_skills = draw(st.integers(min_value=1, max_value=3))
    skills = draw(st.lists(
        st.sampled_from(SKILL_NAMES), min_size=num_skills, max_size=num_skills,
        unique=True,
    ))

    scored_sections = []
    all_code_blocks = []

    for skill_name in skills:
        # 1-2 sections per skill
        num_sections = draw(st.integers(min_value=1, max_value=2))
        for _ in range(num_sections):
            rules = draw(rule_lines())
            code_blocks = draw(code_blocks_strategy())
            all_code_blocks.extend((skill_name, cb) for cb in code_blocks)

            # Build a section body that contains the rules and code block markers
            body_lines = list(rules)
            for cb in code_blocks:
                body_lines.append(cb.preceding_text)
                body_lines.append(f"```{cb.language}")
                body_lines.append(cb.content)
                body_lines.append("```")
            body = "\n".join(body_lines)

            heading = draw(st.lists(
                st.sampled_from(NON_STOP_VOCAB), min_size=1, max_size=3
            ).map(lambda w: " ".join(w)))

            section = Section(
                heading=heading,
                body=body,
                code_blocks=code_blocks,
                is_preamble=False,
            )

            score = draw(st.floats(min_value=0.5, max_value=1.0))
            scored_sections.append(ScoredSection(
                section=section,
                skill_name=skill_name,
                raw_score=score,
                normalized_score=score,
            ))

    assume(len(scored_sections) > 0)
    return (scored_sections, skills, all_code_blocks)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=scored_sections_for_formatting())
def test_all_rules_formatted_as_bullet_points(data):
    """Every non-heading, non-code-fence, non-empty line in the output starts with `- `.

    Property 12 states that every extracted rule SHALL be formatted as a markdown
    bullet point (starting with `- `).
    """
    scored_sections, _skills, _code_blocks = data

    config = DistillConfig(token_budget=16000, threshold=0.0)
    output, _tokens = assemble_prompt(scored_sections, config, always_sections=[])

    if not output.strip():
        return  # Empty output is valid (nothing to check)

    lines = output.split("\n")
    in_code_fence = False

    for line in lines:
        stripped = line.strip()

        # Track code fence state
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue

        # Skip lines inside code fences (they're code content, not rules)
        if in_code_fence:
            continue

        # Skip empty lines
        if not stripped:
            continue

        # Skip skill headings (### SKILL_NAME)
        if stripped.startswith("### "):
            continue

        # Every remaining line should be a bullet point
        assert stripped.startswith("- "), (
            f"Non-bullet content line found in output:\n"
            f"  Line: {stripped!r}\n"
            f"  Expected: line starting with '- '\n"
            f"  Full output:\n{output}"
        )


@settings(max_examples=100)
@given(data=scored_sections_for_formatting())
def test_code_blocks_preserve_language_annotation(data):
    """Every code block in the output has ```language opening and ``` closing,
    with the original language annotation preserved.

    Property 12 states every included code example SHALL be wrapped in a fenced
    code block with its original language annotation preserved.
    """
    scored_sections, _skills, all_code_blocks = data

    config = DistillConfig(token_budget=16000, threshold=0.0)
    output, _tokens = assemble_prompt(scored_sections, config, always_sections=[])

    if not output.strip():
        return

    # Parse code blocks from the output
    lines = output.split("\n")
    output_code_blocks = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```") and stripped != "```":
            # Opening fence with language
            lang = stripped[3:].strip()
            content_lines = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                content_lines.append(lines[i])
                i += 1
            output_code_blocks.append((lang, "\n".join(content_lines)))
        elif stripped == "```":
            # Opening fence WITHOUT language — this would violate the property
            # Only count as code block if it's an opening fence (not closing)
            # We track this by checking if we're not already inside a block
            # Actually closing fences are consumed in the inner while loop above,
            # so a bare ``` here is an opening fence with no language
            content_lines = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                content_lines.append(lines[i])
                i += 1
            output_code_blocks.append(("", "\n".join(content_lines)))
        i += 1

    # Every code block in the output must have a valid opening fence with language
    for lang, content in output_code_blocks:
        assert lang != "", (
            f"Code block found without language annotation:\n"
            f"  Content: {content[:80]!r}...\n"
            f"  Full output:\n{output}"
        )

    # Collect all input language annotations as a set of valid languages
    input_languages = {cb.language for _, cb in all_code_blocks if cb.language}

    # Every language annotation in the output must come from one of the input code blocks
    for lang, _content in output_code_blocks:
        assert lang in input_languages, (
            f"Unknown language annotation in output:\n"
            f"  Found: {lang!r}\n"
            f"  Expected one of: {input_languages}\n"
            f"  Full output:\n{output}"
        )


@settings(max_examples=100)
@given(data=scored_sections_for_formatting())
def test_skill_blocks_have_uppercase_heading(data):
    """Each skill block begins with `### SKILL_NAME` where SKILL_NAME is the
    uppercase frontmatter name.

    Property 12 states each skill block SHALL begin with `### SKILL_NAME` where
    SKILL_NAME is the uppercase frontmatter name.
    """
    scored_sections, skills, _code_blocks = data

    config = DistillConfig(token_budget=16000, threshold=0.0)
    output, _tokens = assemble_prompt(scored_sections, config, always_sections=[])

    if not output.strip():
        return

    # Extract all ### headings from output
    heading_pattern = re.compile(r"^### (.+)$", re.MULTILINE)
    headings_found = heading_pattern.findall(output)

    # Every heading must be fully uppercase
    for heading in headings_found:
        assert heading == heading.upper(), (
            f"Skill heading not uppercase:\n"
            f"  Found: '### {heading}'\n"
            f"  Expected: '### {heading.upper()}'\n"
            f"  Full output:\n{output}"
        )

    # Every skill that contributed sections must have its heading present
    for skill_name in skills:
        expected_heading = skill_name.upper()
        assert expected_heading in headings_found, (
            f"Skill '{skill_name}' missing its heading in output:\n"
            f"  Expected heading: '### {expected_heading}'\n"
            f"  Found headings: {headings_found}\n"
            f"  Full output:\n{output}"
        )
