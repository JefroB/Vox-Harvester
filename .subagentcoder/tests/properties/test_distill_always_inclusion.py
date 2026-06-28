# Feature: skill-distillation, Property 2: Always-tagged inclusion guarantee
"""Property-based tests for always-tagged inclusion guarantee.

**Validates: Requirements 1.3**

For any task description and any set of skill files where at least one is tagged
"always", the Distilled_Prompt SHALL contain the first level-2 Section of every
"always"-tagged Skill_File, regardless of its Relevance_Score (subject only to
token budget).
"""

import sys
import tempfile
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import distill, DistillConfig, estimate_tokens


# --- Strategies ---

# Fixed vocabulary for generating task descriptions (intentionally unrelated
# to skill content to prove always-tagged inclusion is score-independent)
TASK_VOCAB = [
    "quantum", "photosynthesis", "archaeology", "submarine", "philosophy",
    "astronomy", "geology", "origami", "meteorology", "cartography",
    "linguistics", "botany", "oceanography", "thermodynamics", "paleontology",
    "cryptocurrency", "volleyball", "typography", "zoology", "ceramics",
    "python", "function", "validate", "security", "database",
    "deploy", "testing", "build", "server", "endpoint",
]

# Vocabulary for skill section content
SKILL_VOCAB = [
    "code", "review", "testing", "coverage", "lint",
    "format", "indent", "naming", "convention", "module",
    "class", "function", "variable", "constant", "import",
    "export", "interface", "abstract", "pattern", "design",
]

# Generate random task descriptions (1-15 words from mixed vocab)
task_description_strategy = st.lists(
    st.sampled_from(TASK_VOCAB),
    min_size=1,
    max_size=15,
).map(lambda words: " ".join(words))

# Generate random section heading (1-4 words)
section_heading_strategy = st.lists(
    st.sampled_from(SKILL_VOCAB),
    min_size=1,
    max_size=4,
).map(lambda words: " ".join(words))

# Generate random section body lines (bullet points to ensure extractable rules)
section_body_strategy = st.lists(
    st.lists(
        st.sampled_from(SKILL_VOCAB),
        min_size=2,
        max_size=8,
    ).map(lambda words: "- " + " ".join(words)),
    min_size=1,
    max_size=6,
).map(lambda lines: "\n".join(lines))


@st.composite
def always_tagged_skill(draw):
    """Generate a skill file content with 'always' tag and at least one ## section."""
    skill_name = draw(st.sampled_from([
        "Core Standards", "Engineering Rules", "Quality Guide",
        "Best Practices", "Development Standards",
    ]))

    # Generate 1-3 sections (## headings)
    num_sections = draw(st.integers(min_value=1, max_value=3))
    sections = []
    for _ in range(num_sections):
        heading = draw(section_heading_strategy)
        body = draw(section_body_strategy)
        sections.append((heading, body))

    # Build skill file content
    lines = [
        "---",
        f"name: {skill_name}",
        "tags: [always]",
        f"description: Auto-generated always-tagged skill.",
        "---",
        "",
        f"# {skill_name}",
        "",
        "Preamble content for the skill.",
        "",
    ]
    for heading, body in sections:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body)
        lines.append("")

    content = "\n".join(lines)
    # Return (skill_name, first_section_heading, first_section_body, file_content)
    return (skill_name, sections[0][0], sections[0][1], content)


@st.composite
def non_always_skill(draw):
    """Generate a skill file without 'always' tag."""
    skill_name = draw(st.sampled_from([
        "Optional Skill", "Extra Guide", "Advanced Tips",
        "Performance Notes", "Security Checklist",
    ]))

    heading = draw(section_heading_strategy)
    body = draw(section_body_strategy)

    lines = [
        "---",
        f"name: {skill_name}",
        "tags: [code]",
        f"description: Auto-generated non-always skill.",
        "---",
        "",
        f"# {skill_name}",
        "",
        "Preamble for optional skill.",
        "",
        f"## {heading}",
        "",
        body,
        "",
    ]
    content = "\n".join(lines)
    return (skill_name, content)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    task_desc=task_description_strategy,
    always_skill=always_tagged_skill(),
)
def test_always_skill_name_appears_in_output(task_desc, always_skill):
    """The always-tagged skill's name (uppercased) appears as ### SKILL_NAME in output."""
    skill_name, first_heading, first_body, content = always_skill

    # Write skill to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        skill_path = Path(f.name)

    try:
        # Use a large budget so budget isn't the limiting factor
        config = DistillConfig(token_budget=16000, threshold=0.99)
        result = distill(task_desc, [skill_path], config)

        # The always skill name uppercased must appear in the output
        assert f"### {skill_name.upper()}" in result.prompt, (
            f"Expected '### {skill_name.upper()}' in output but not found.\n"
            f"Task: {task_desc!r}\n"
            f"Output:\n{result.prompt}"
        )
    finally:
        skill_path.unlink(missing_ok=True)


@settings(max_examples=100)
@given(
    task_desc=task_description_strategy,
    always_skill=always_tagged_skill(),
)
def test_always_first_section_content_in_output(task_desc, always_skill):
    """Content from the first ## section of the always-tagged skill appears in output."""
    skill_name, first_heading, first_body, content = always_skill

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        skill_path = Path(f.name)

    try:
        # Large budget, high threshold (to prove always inclusion is independent of score)
        config = DistillConfig(token_budget=16000, threshold=0.99)
        result = distill(task_desc, [skill_path], config)

        # Extract the bullet points from first section body
        # At least some of the rules from the first section should appear
        body_lines = [
            line.strip() for line in first_body.split("\n")
            if line.strip().startswith("- ")
        ]
        assume(len(body_lines) > 0)

        # At least one rule from the first section should be present in the output
        found_any_rule = False
        for rule_line in body_lines:
            # The rule content (without leading "- ") should appear in output
            rule_text = rule_line[2:]  # strip "- " prefix
            if rule_text in result.prompt:
                found_any_rule = True
                break

        assert found_any_rule, (
            f"No content from always-tagged skill's first section found in output.\n"
            f"Task: {task_desc!r}\n"
            f"First section rules: {body_lines}\n"
            f"Output:\n{result.prompt}"
        )
    finally:
        skill_path.unlink(missing_ok=True)


@settings(max_examples=100)
@given(
    task_desc=task_description_strategy,
    always_skill=always_tagged_skill(),
    other_skill=non_always_skill(),
)
def test_always_inclusion_regardless_of_other_skills(task_desc, always_skill, other_skill):
    """Always-tagged skill is included even when other non-always skills are present."""
    skill_name, first_heading, first_body, always_content = always_skill
    other_name, other_content = other_skill

    # Write both skills to temp files
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f1:
        f1.write(always_content)
        always_path = Path(f1.name)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f2:
        f2.write(other_content)
        other_path = Path(f2.name)

    try:
        # Large budget, high threshold — the always skill should still appear
        # even though the task is unrelated (high threshold filters out everything else)
        config = DistillConfig(token_budget=16000, threshold=0.99)
        result = distill(task_desc, [always_path, other_path], config)

        # The always skill must be in the output regardless of task description
        assert f"### {skill_name.upper()}" in result.prompt, (
            f"Always-tagged skill '{skill_name}' missing from output "
            f"when other skills are present.\n"
            f"Task: {task_desc!r}\n"
            f"Output:\n{result.prompt}"
        )
    finally:
        always_path.unlink(missing_ok=True)
        other_path.unlink(missing_ok=True)


@settings(max_examples=100)
@given(
    task_desc=task_description_strategy,
    always_skill=always_tagged_skill(),
)
def test_always_inclusion_with_totally_unrelated_task(task_desc, always_skill):
    """Always-tagged skill is included even for completely unrelated task descriptions.

    This verifies the 'regardless of Relevance_Score' part of the property.
    We use a high threshold (0.99) to ensure no section would pass by score alone,
    proving the inclusion is truly independent of relevance scoring.
    """
    skill_name, first_heading, first_body, content = always_skill

    # Prepend unrelated gibberish to task to minimize any accidental keyword overlap
    unrelated_task = f"zzzyyyxxx {task_desc} qqqwwweee"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        skill_path = Path(f.name)

    try:
        config = DistillConfig(token_budget=16000, threshold=0.99)
        result = distill(unrelated_task, [skill_path], config)

        # Must still contain the always skill
        assert f"### {skill_name.upper()}" in result.prompt, (
            f"Always-tagged skill not included for unrelated task.\n"
            f"Task: {unrelated_task!r}\n"
            f"Skill: {skill_name}\n"
            f"Output:\n{result.prompt}"
        )
    finally:
        skill_path.unlink(missing_ok=True)
