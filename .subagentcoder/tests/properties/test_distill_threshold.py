# Feature: skill-distillation, Property 3: Threshold exclusion invariant
"""Property-based tests for threshold exclusion.

**Validates: Requirements 1.4, 1.5**

For any task description, skill file set, and threshold value, no Section whose
Relevance_Score is below the configured threshold SHALL appear in the
Distilled_Prompt (excluding "always"-tagged core sections). If all Sections of a
non-mandatory Skill_File score below the threshold, that Skill_File SHALL be
entirely absent from the output.
"""

import sys
import tempfile
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import (
    distill,
    score_section,
    DistillConfig,
    DEFAULT_STOP_WORDS,
    parse_skill_file,
)


# --- Strategies ---

# Use a controlled vocabulary for predictable scoring behavior.
# These words are NOT stop words and are long enough to avoid overlap.
VOCAB = [
    "python", "function", "validate", "input", "security",
    "database", "query", "server", "client", "module",
    "parse", "token", "config", "error", "handler",
    "cache", "async", "deploy", "testing", "build",
    "route", "middleware", "schema", "model", "endpoint",
    "logging", "metrics", "tracing", "observability", "monitoring",
    "refactor", "architecture", "interface", "abstract", "pattern",
]

# Words disjoint from VOCAB to create content that won't match certain tasks
DISJOINT_VOCAB = [
    "xylophone", "zeppelin", "quartz", "vortex", "nebula",
    "platypus", "fjord", "glyph", "sphinx", "rhythm",
    "crypt", "nymph", "lymph", "psych", "synth",
]

# Task description: 2-6 words from VOCAB
task_strategy = st.lists(
    st.sampled_from(VOCAB), min_size=2, max_size=6
).map(lambda words: " ".join(words))

# Threshold: float in [0.0, 1.0]
threshold_strategy = st.floats(min_value=0.0, max_value=1.0)

# Section heading: 1-3 words
heading_strategy = st.lists(
    st.sampled_from(VOCAB + DISJOINT_VOCAB), min_size=1, max_size=3
).map(lambda words: " ".join(words))

# Section body using disjoint vocab (low relevance to task)
low_relevance_body = st.lists(
    st.sampled_from(DISJOINT_VOCAB), min_size=3, max_size=15
).map(lambda words: "- " + "\n- ".join(words))

# Section body using VOCAB (higher relevance to task)
high_relevance_body = st.lists(
    st.sampled_from(VOCAB), min_size=3, max_size=15
).map(lambda words: "- " + "\n- ".join(words))


def _build_skill_file(name: str, tags: list[str], sections: list[tuple[str, str]]) -> str:
    """Build a skill file with given name, tags, and sections (heading, body) list."""
    tags_str = "[" + ", ".join(tags) + "]"
    sections_text = "\n\n".join(f"## {h}\n\n{b}" for h, b in sections)
    return f"""---
name: {name}
tags: {tags_str}
description: Test skill for threshold property testing.
---

# {name}

{sections_text}
"""


@st.composite
def skill_with_unique_markers(draw, skill_index: int):
    """Generate a skill file where each section has a unique marker word.

    The marker is a unique identifier that won't appear in any other section
    or in the output's metadata, allowing precise detection of section inclusion.
    """
    base_names = [
        "TestSkill", "CodeGuide", "SecurityRules", "DataPatterns", "BuildTools"
    ]
    name = f"{draw(st.sampled_from(base_names))}{skill_index}"

    num_sections = draw(st.integers(min_value=1, max_value=3))
    sections = []
    markers = []

    for sec_idx in range(num_sections):
        heading = draw(heading_strategy)
        # Create a unique marker for this section
        marker = f"uniquemarker{skill_index}sec{sec_idx}"
        # Build body with the marker as a bullet point
        body_words = draw(st.lists(
            st.sampled_from(DISJOINT_VOCAB + VOCAB), min_size=2, max_size=8
        ))
        body = f"- {marker}\n- " + "\n- ".join(body_words)
        sections.append((heading, body))
        markers.append(marker)

    content = _build_skill_file(name, ["code"], sections)
    return (name, content, markers)


@st.composite
def skill_disjoint_with_markers(draw, skill_index: int):
    """Generate a skill file using DISJOINT_VOCAB content with unique markers."""
    base_names = [
        "TestSkill", "CodeGuide", "SecurityRules", "DataPatterns", "BuildTools"
    ]
    name = f"{draw(st.sampled_from(base_names))}{skill_index}"

    num_sections = draw(st.integers(min_value=1, max_value=3))
    sections = []
    markers = []

    for sec_idx in range(num_sections):
        # Use disjoint vocab for headings to ensure low scores against VOCAB tasks
        heading = draw(st.lists(
            st.sampled_from(DISJOINT_VOCAB), min_size=1, max_size=3
        ).map(lambda words: " ".join(words)))
        marker = f"uniquemarker{skill_index}sec{sec_idx}"
        body_words = draw(st.lists(
            st.sampled_from(DISJOINT_VOCAB), min_size=2, max_size=8
        ))
        body = f"- {marker}\n- " + "\n- ".join(body_words)
        sections.append((heading, body))
        markers.append(marker)

    content = _build_skill_file(name, ["code"], sections)
    return (name, content, markers)


@st.composite
def always_skill_file_content(draw):
    """Generate a skill file tagged 'always'."""
    name = draw(st.sampled_from([
        "CorePrinciples", "AlwaysActive", "BaseRules"
    ]))
    heading = draw(heading_strategy)
    body = draw(low_relevance_body)

    content = _build_skill_file(name, ["always"], [(heading, body)])
    return (name, content)


@st.composite
def indexed_skill_list_with_markers(draw, min_size: int = 1, max_size: int = 3):
    """Generate a list of skill files with unique markers per section."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    skills = []
    for i in range(count):
        skill = draw(skill_with_unique_markers(skill_index=i))
        skills.append(skill)
    return skills


@st.composite
def indexed_disjoint_skill_list_with_markers(draw, min_size: int = 1, max_size: int = 3):
    """Generate a list of disjoint-vocab skill files with unique markers."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    skills = []
    for i in range(count):
        skill = draw(skill_disjoint_with_markers(skill_index=i))
        skills.append(skill)
    return skills


# --- Helpers ---

def write_skill_file(tmp_dir: Path, filename: str, content: str) -> Path:
    """Write a skill file to a temporary directory and return its path."""
    path = tmp_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def preprocess_task_tokens(task_description: str) -> set[str]:
    """Compute task tokens the same way distill() does."""
    return {
        w.lower()
        for w in task_description.split()
        if w.lower() not in DEFAULT_STOP_WORDS
    }


# --- Property Tests ---


@settings(max_examples=100)
@given(
    task_desc=task_strategy,
    threshold=threshold_strategy,
    skill_data=indexed_skill_list_with_markers(),
)
def test_below_threshold_sections_excluded_from_output(task_desc, threshold, skill_data):
    """No section scoring below threshold appears in the distilled output.

    For each skill file, compute scores manually. Any section whose unique marker
    is below threshold must NOT appear in the output (unless it's an always-tagged
    core section).
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        skill_paths = []

        for i, (name, content, markers) in enumerate(skill_data):
            path = write_skill_file(tmp_path, f"skill_{i}.md", content)
            skill_paths.append(path)

        config = DistillConfig(
            token_budget=16000,  # Large budget so budget doesn't exclude sections
            threshold=threshold,
        )

        result = distill(task_desc, skill_paths, config)
        output = result.prompt

        # Now verify: for each skill file, compute section scores
        # and check that below-threshold sections' markers are absent from output
        task_tokens = preprocess_task_tokens(task_desc)

        for i, (name, content, markers) in enumerate(skill_data):
            path = skill_paths[i]
            parsed_name, tags, sections = parse_skill_file(path)

            # Skip always-tagged skills (they get special treatment)
            if "always" in tags:
                continue

            # Match markers to non-preamble sections
            non_preamble_sections = [s for s in sections if not s.is_preamble]

            for sec_idx, section in enumerate(non_preamble_sections):
                if sec_idx >= len(markers):
                    break

                score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)
                marker = markers[sec_idx]

                if score < threshold:
                    # This section's unique marker should NOT appear in output
                    assert marker not in output, (
                        f"Section '{section.heading}' (skill '{parsed_name}') scored "
                        f"{score} < threshold {threshold} but its unique marker "
                        f"'{marker}' appears in output.\n"
                        f"Task: '{task_desc}'"
                    )


@settings(max_examples=100)
@given(
    task_desc=task_strategy,
    threshold=threshold_strategy,
    skill_data=indexed_disjoint_skill_list_with_markers(),
)
def test_all_below_threshold_skill_entirely_absent(task_desc, threshold, skill_data):
    """If all sections of a non-mandatory skill score below threshold, that skill is absent.

    When every section of a non-always Skill_File has Relevance_Score < threshold,
    the skill name (as ### SKILL_NAME) SHALL NOT appear in the output.
    """
    # Use a positive threshold so it's possible for sections to fall below
    assume(threshold > 0.0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        skill_paths = []

        for i, (name, content, markers) in enumerate(skill_data):
            path = write_skill_file(tmp_path, f"skill_{i}.md", content)
            skill_paths.append(path)

        config = DistillConfig(
            token_budget=16000,
            threshold=threshold,
        )

        result = distill(task_desc, skill_paths, config)
        output = result.prompt

        # Verify: for each skill, if ALL sections score below threshold,
        # the skill's heading must not appear in output
        task_tokens = preprocess_task_tokens(task_desc)

        for path in skill_paths:
            name, tags, sections = parse_skill_file(path)

            if "always" in tags:
                continue

            # Compute scores for all sections (including preamble)
            all_below = True
            for section in sections:
                score = score_section(task_tokens, section, DEFAULT_STOP_WORDS)
                if score >= threshold:
                    all_below = False
                    break

            if all_below:
                # The skill name heading should NOT appear in output
                skill_heading = f"### {name.upper()}"
                assert skill_heading not in output, (
                    f"Skill '{name}' has all sections below threshold {threshold} "
                    f"but '### {name.upper()}' still appears in output.\n"
                    f"Task: '{task_desc}'"
                )


@settings(max_examples=100)
@given(
    task_desc=task_strategy,
    threshold=threshold_strategy,
    regular_skill=indexed_skill_list_with_markers(min_size=1, max_size=1),
    always_skill=always_skill_file_content(),
)
def test_always_tagged_core_section_exempt_from_threshold(
    task_desc, threshold, regular_skill, always_skill
):
    """Always-tagged core sections appear in output regardless of their score.

    The first level-2 Section of an always-tagged Skill_File is included even if
    its Relevance_Score is below the threshold (subject only to budget).
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        reg_name, reg_content, _ = regular_skill[0]
        always_name, always_content = always_skill

        reg_path = write_skill_file(tmp_path, "regular_skill.md", reg_content)
        always_path = write_skill_file(tmp_path, "always_skill.md", always_content)

        config = DistillConfig(
            token_budget=16000,
            threshold=threshold,
        )

        result = distill(task_desc, [reg_path, always_path], config)
        output = result.prompt

        # The always skill's heading should appear in output regardless of score
        # (provided budget allows it, which it does at 16000)
        always_heading = f"### {always_name.upper()}"

        # Verify the always skill's core section is present
        _, always_tags, _ = parse_skill_file(always_path)
        assert "always" in always_tags, "Test setup error: skill not tagged 'always'"

        # The always skill heading should be in output
        assert always_heading in output, (
            f"Always-tagged skill '{always_name}' should appear in output "
            f"regardless of threshold ({threshold}), but '{always_heading}' is absent.\n"
            f"Task: '{task_desc}'\nOutput: '{output[:200]}...'"
        )
