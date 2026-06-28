# Feature: skill-distillation, Property 4: Score normalization preserves ordering
"""Property-based tests for score normalization.

**Validates: Requirements 1.6**

For any Skill_File with at least one Section scoring above the threshold, the
normalized scores SHALL have the highest-scoring Section at 1.0, all others
proportionally scaled, and the relative ordering of Sections by score SHALL be
preserved after normalization.
"""

import sys
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import normalize_scores, ScoredSection, Section, CodeBlock


# --- Strategies ---

# Strategy for generating positive raw scores (already filtered by threshold)
positive_float = st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for skill names
skill_name_strategy = st.sampled_from([
    "software-engineering", "security", "api-design",
    "testing-strategy", "performance", "documentation",
    "error-handling", "refactoring",
])


def make_scored_section(skill_name: str, raw_score: float) -> ScoredSection:
    """Create a ScoredSection with minimal section data for normalization testing."""
    section = Section(
        heading=f"Section with score {raw_score:.2f}",
        body="Some body content",
        code_blocks=[],
        is_preamble=False,
    )
    return ScoredSection(
        section=section,
        skill_name=skill_name,
        raw_score=raw_score,
        normalized_score=0.0,  # Will be set by normalize_scores
    )


@st.composite
def single_skill_sections(draw):
    """Generate a list of ScoredSections for a single skill with distinct raw scores."""
    skill_name = draw(skill_name_strategy)
    num_sections = draw(st.integers(min_value=1, max_value=10))
    raw_scores = draw(
        st.lists(positive_float, min_size=num_sections, max_size=num_sections)
    )
    sections = [make_scored_section(skill_name, score) for score in raw_scores]
    return sections


@st.composite
def multi_skill_sections(draw):
    """Generate ScoredSections spanning multiple skill files."""
    num_skills = draw(st.integers(min_value=1, max_value=4))
    all_skills = ["software-engineering", "security", "api-design",
                  "testing-strategy", "performance", "documentation",
                  "error-handling", "refactoring"]
    chosen_skills = draw(
        st.lists(
            st.sampled_from(all_skills),
            min_size=num_skills,
            max_size=num_skills,
            unique=True,
        )
    )

    sections = []
    for skill_name in chosen_skills:
        num_sections = draw(st.integers(min_value=1, max_value=6))
        raw_scores = draw(
            st.lists(positive_float, min_size=num_sections, max_size=num_sections)
        )
        for score in raw_scores:
            sections.append(make_scored_section(skill_name, score))

    return sections


# --- Property Tests ---


@settings(max_examples=100)
@given(sections=single_skill_sections())
def test_highest_score_normalized_to_one(sections):
    """The highest-scoring section per skill gets normalized_score == 1.0."""
    result = normalize_scores(sections)

    # Group by skill name
    groups: dict[str, list[ScoredSection]] = {}
    for ss in result:
        groups.setdefault(ss.skill_name, []).append(ss)

    for skill_name, group in groups.items():
        max_raw = max(ss.raw_score for ss in group)
        # All sections with the max raw score should have normalized_score == 1.0
        for ss in group:
            if ss.raw_score == max_raw:
                assert ss.normalized_score == 1.0, (
                    f"Highest-scoring section in '{skill_name}' has "
                    f"normalized_score={ss.normalized_score}, expected 1.0. "
                    f"raw_score={ss.raw_score}, max_raw={max_raw}"
                )


@settings(max_examples=100)
@given(sections=single_skill_sections())
def test_all_normalized_scores_in_valid_range(sections):
    """All normalized_scores are in (0.0, 1.0] for positive raw scores."""
    result = normalize_scores(sections)

    for ss in result:
        assert 0.0 < ss.normalized_score <= 1.0, (
            f"normalized_score={ss.normalized_score} out of range (0.0, 1.0] "
            f"for skill '{ss.skill_name}', raw_score={ss.raw_score}"
        )


@settings(max_examples=100)
@given(sections=single_skill_sections())
def test_relative_ordering_preserved(sections):
    """If raw_score_a > raw_score_b, then normalized_score_a > normalized_score_b."""
    result = normalize_scores(sections)

    # Group by skill name
    groups: dict[str, list[ScoredSection]] = {}
    for ss in result:
        groups.setdefault(ss.skill_name, []).append(ss)

    for skill_name, group in groups.items():
        # Check all pairs
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.raw_score > b.raw_score:
                    assert a.normalized_score > b.normalized_score, (
                        f"Ordering violated in '{skill_name}': "
                        f"raw {a.raw_score} > {b.raw_score} but "
                        f"normalized {a.normalized_score} <= {b.normalized_score}"
                    )
                elif a.raw_score < b.raw_score:
                    assert a.normalized_score < b.normalized_score, (
                        f"Ordering violated in '{skill_name}': "
                        f"raw {a.raw_score} < {b.raw_score} but "
                        f"normalized {a.normalized_score} >= {b.normalized_score}"
                    )
                else:
                    # Equal raw scores should give equal normalized scores
                    assert a.normalized_score == b.normalized_score, (
                        f"Equal raw scores in '{skill_name}' ({a.raw_score}) "
                        f"gave different normalized scores: "
                        f"{a.normalized_score} vs {b.normalized_score}"
                    )


@settings(max_examples=100)
@given(sections=multi_skill_sections())
def test_proportional_scaling(sections):
    """normalized_score == raw_score / max_raw_score for each skill group."""
    result = normalize_scores(sections)

    # Group by skill name
    groups: dict[str, list[ScoredSection]] = {}
    for ss in result:
        groups.setdefault(ss.skill_name, []).append(ss)

    for skill_name, group in groups.items():
        max_raw = max(ss.raw_score for ss in group)
        assert max_raw > 0, f"All raw scores are 0 for '{skill_name}'"

        for ss in group:
            expected = ss.raw_score / max_raw
            assert abs(ss.normalized_score - expected) < 1e-10, (
                f"Proportional scaling failed in '{skill_name}': "
                f"raw_score={ss.raw_score}, max_raw={max_raw}, "
                f"expected normalized={expected}, got {ss.normalized_score}"
            )
