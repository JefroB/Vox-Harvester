# Feature: skill-distillation, Property 11: Output skill blocks ordered by maximum section score
"""Property-based tests for output ordering.

**Validates: Requirements 6.1, 2.4**

For any distillation result containing multiple skill blocks, the skill blocks
SHALL appear in descending order of their highest Section Relevance_Score. Within
each skill block, Sections SHALL appear in descending Relevance_Score order.
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

# Skill names pool (distinct names for generating multi-skill scenarios)
SKILL_NAMES = [
    "software-engineering", "security", "api-design",
    "testing-strategy", "performance", "documentation",
    "error-handling", "refactoring",
]

# Vocabulary of non-stop words for generating extractable bullet content
NON_STOP_VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
    "cache", "async", "deploy", "testing", "build",
]


def make_section_with_bullets(heading: str, num_bullets: int = 3) -> Section:
    """Create a Section with bullet lines so extract_rules produces content."""
    bullets = [f"- Use {NON_STOP_VOCAB[i % len(NON_STOP_VOCAB)]} properly" for i in range(num_bullets)]
    body = "\n".join(bullets)
    return Section(
        heading=heading,
        body=body,
        code_blocks=[],
        is_preamble=False,
    )


def make_scored_section(skill_name: str, normalized_score: float, heading_suffix: str = "") -> ScoredSection:
    """Create a ScoredSection with extractable content and a given normalized score."""
    heading = f"{skill_name} section {heading_suffix}".strip()
    section = make_section_with_bullets(heading)
    return ScoredSection(
        section=section,
        skill_name=skill_name,
        raw_score=normalized_score,  # For ordering tests, raw == normalized is fine
        normalized_score=normalized_score,
    )


@st.composite
def multi_skill_scored_sections(draw):
    """Generate scored sections from multiple distinct skills with distinct max scores.

    Returns a list of ScoredSections where:
    - At least 2 different skill names are present
    - Each skill has 1-3 sections with different normalized_scores
    - Max scores across skills are all distinct (to avoid tie-breaking ambiguity)
    """
    num_skills = draw(st.integers(min_value=2, max_value=5))
    chosen_skills = draw(
        st.lists(
            st.sampled_from(SKILL_NAMES),
            min_size=num_skills,
            max_size=num_skills,
            unique=True,
        )
    )

    # Generate distinct max scores for each skill (one per skill, all different)
    max_scores = draw(
        st.lists(
            st.floats(min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=num_skills,
            max_size=num_skills,
            unique=True,
        )
    )

    sections: list[ScoredSection] = []
    for skill_name, max_score in zip(chosen_skills, max_scores):
        num_sections = draw(st.integers(min_value=1, max_value=3))
        # Generate scores for this skill: one is the max, others are lower
        skill_scores = [max_score]
        for i in range(num_sections - 1):
            lower_score = draw(
                st.floats(
                    min_value=0.1,
                    max_value=max_score - 0.01,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            skill_scores.append(lower_score)

        for idx, score in enumerate(skill_scores):
            ss = make_scored_section(skill_name, score, heading_suffix=f"part{idx}")
            sections.append(ss)

    return sections


@st.composite
def single_skill_multiple_sections(draw):
    """Generate multiple sections for a single skill with distinct normalized scores.

    Returns a list of ScoredSections for one skill, each with a different score.
    Each section has unique distinguishable content (marker in the body).
    """
    skill_name = draw(st.sampled_from(SKILL_NAMES))
    num_sections = draw(st.integers(min_value=2, max_value=5))

    scores = draw(
        st.lists(
            st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=num_sections,
            max_size=num_sections,
            unique=True,
        )
    )

    sections: list[ScoredSection] = []
    for idx, score in enumerate(scores):
        heading = f"{skill_name} section part{idx}"
        # Give each section a unique body so we can find it in the output
        body = f"- Rule marker{idx} validate input"
        section = Section(
            heading=heading,
            body=body,
            code_blocks=[],
            is_preamble=False,
        )
        ss = ScoredSection(
            section=section,
            skill_name=skill_name,
            raw_score=score,
            normalized_score=score,
        )
        sections.append(ss)

    return sections


# --- Property Tests ---


@settings(max_examples=100)
@given(scored_sections=multi_skill_scored_sections())
def test_skill_blocks_ordered_by_max_section_score(scored_sections):
    """Skill block headings (### SKILL_NAME) appear in descending order of
    their skill's maximum normalized section score."""
    config = DistillConfig(token_budget=16000, threshold=0.0)

    prompt, _tokens = assemble_prompt(scored_sections, config, always_sections=[])

    # Skip if prompt is empty (no extractable content)
    assume(prompt.strip() != "")

    # Extract ### HEADING lines in order of appearance
    heading_pattern = re.compile(r"^### (.+)$", re.MULTILINE)
    headings_in_output = heading_pattern.findall(prompt)

    # Skip if fewer than 2 skill blocks made it into output
    assume(len(headings_in_output) >= 2)

    # Compute expected max score per skill
    skill_max_scores: dict[str, float] = {}
    for ss in scored_sections:
        current = skill_max_scores.get(ss.skill_name, 0.0)
        if ss.normalized_score > current:
            skill_max_scores[ss.skill_name] = ss.normalized_score

    # Map headings back to skill names (headings are UPPERCASE of skill_name)
    skill_name_by_heading: dict[str, str] = {}
    for ss in scored_sections:
        skill_name_by_heading[ss.skill_name.upper()] = ss.skill_name

    # Get the max scores in the order they appear in the output
    output_max_scores = []
    for heading in headings_in_output:
        skill_name = skill_name_by_heading.get(heading)
        if skill_name is not None:
            output_max_scores.append(skill_max_scores[skill_name])

    # Verify descending order
    for i in range(len(output_max_scores) - 1):
        assert output_max_scores[i] >= output_max_scores[i + 1], (
            f"Skill blocks not in descending max-score order:\n"
            f"  Headings: {headings_in_output}\n"
            f"  Max scores in output order: {output_max_scores}\n"
            f"  Position {i}: {output_max_scores[i]} should be >= {output_max_scores[i + 1]}"
        )


@settings(max_examples=100)
@given(scored_sections=single_skill_multiple_sections())
def test_within_skill_descending_score_order(scored_sections):
    """Within a single skill, sections are included in descending normalized_score order.

    Each section has a unique marker in its body. We verify the markers appear
    in the output in score-descending order.
    """
    config = DistillConfig(token_budget=16000, threshold=0.0)

    prompt, _tokens = assemble_prompt(scored_sections, config, always_sections=[])

    # Skip if prompt is empty
    assume(prompt.strip() != "")

    # Get expected order: descending by normalized_score
    sorted_by_score = sorted(
        enumerate(scored_sections),
        key=lambda pair: -pair[1].normalized_score,
    )

    # Find positions of each marker in the output
    marker_positions: list[tuple[int, float]] = []
    for orig_idx, ss in sorted_by_score:
        marker = f"Rule marker{orig_idx}"
        pos = prompt.find(marker)
        if pos >= 0:
            marker_positions.append((pos, ss.normalized_score))

    # Need at least 2 markers in output to verify ordering
    assume(len(marker_positions) >= 2)

    # Verify that positions are in ascending order (earlier in text = higher score)
    for i in range(len(marker_positions) - 1):
        pos_a, score_a = marker_positions[i]
        pos_b, score_b = marker_positions[i + 1]
        assert pos_a < pos_b, (
            f"Within-skill ordering violated:\n"
            f"  Section with score {score_a} at position {pos_a}\n"
            f"  Section with score {score_b} at position {pos_b}\n"
            f"  Expected higher-scored section to appear first"
        )
