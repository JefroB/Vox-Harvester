# Feature: skill-distillation, Property 10: Frontmatter excluded, preamble captured
"""Property-based tests for frontmatter exclusion and preamble capture.

**Validates: Requirements 7.2, 7.6**

For any skill file with YAML frontmatter (between `---` markers at file start),
no frontmatter content SHALL appear in any parsed Section body. Content between
the closing `---` and the first `## ` heading SHALL be captured as a preamble
Section.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import parse_skill_file, Section


# --- Strategies ---

# Frontmatter field values: printable text without --- lines or newlines
_safe_value = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"), blacklist_characters="\r\n"),
    min_size=1,
    max_size=40,
).filter(lambda s: "---" not in s and s.strip())

# Name for frontmatter (stripped — YAML unquoted scalars strip surrounding ws)
name_strategy = _safe_value.map(lambda s: s.strip())

# Tags: list of simple tag words
tag_strategy = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=15).filter(lambda s: s.strip()),
    min_size=0,
    max_size=4,
)

# Extra frontmatter lines (description, arbitrary keys)
extra_fm_line_strategy = st.tuples(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12),
    _safe_value,
).map(lambda kv: f"{kv[0]}: {kv[1]}")

# Preamble content: text between closing --- and first ## heading
# Must not contain ## at line start (that would be a heading)
# Must contain non-whitespace content (implementation skips empty preambles)
_preamble_line = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"), blacklist_characters="\r\n#"),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip())

preamble_strategy = st.lists(_preamble_line, min_size=1, max_size=5).map(lambda lines: "\n".join(lines))

# Section heading text (after ##)
heading_text_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S"), blacklist_characters="\r\n#"),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Section body lines (must not start with ## )
section_body_line = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"), blacklist_characters="\r\n"),
    min_size=0,
    max_size=60,
).filter(lambda s: not s.startswith("## ") and "```" not in s)

# Whether to include ## headings after the preamble
has_headings_strategy = st.booleans()


# --- Helpers ---

def build_skill_file(
    name: str,
    tags: list[str],
    extra_fm_lines: list[str],
    preamble: str,
    headings: list[tuple[str, list[str]]],  # list of (heading_text, body_lines)
) -> str:
    """Build a complete skill file string with frontmatter, preamble, and optional sections."""
    lines = []
    # Frontmatter
    lines.append("---")
    lines.append(f"name: {name}")
    if tags:
        lines.append(f"tags: [{', '.join(tags)}]")
    for fm_line in extra_fm_lines:
        lines.append(fm_line)
    lines.append("---")
    # Preamble
    lines.append("")
    lines.append(preamble)
    # Sections with ## headings
    for heading_text, body_lines in headings:
        lines.append("")
        lines.append(f"## {heading_text}")
        for body_line in body_lines:
            lines.append(body_line)
    return "\n".join(lines)


def get_frontmatter_content(file_text: str) -> str:
    """Extract the raw frontmatter content (between --- markers) from a file."""
    text_lines = file_text.split("\n")
    if not text_lines or text_lines[0].strip() != "---":
        return ""
    for i in range(1, len(text_lines)):
        if text_lines[i].strip() == "---":
            return "\n".join(text_lines[1:i])
    return ""


# --- Property Tests ---


@settings(max_examples=100)
@given(
    name=name_strategy,
    tags=tag_strategy,
    extra_fm_lines=st.lists(extra_fm_line_strategy, min_size=0, max_size=3),
    preamble=preamble_strategy,
    headings=st.lists(
        st.tuples(heading_text_strategy, st.lists(section_body_line, min_size=1, max_size=3)),
        min_size=1,
        max_size=3,
    ),
)
def test_frontmatter_not_in_section_bodies(name, tags, extra_fm_lines, preamble, headings):
    """No frontmatter content SHALL appear in any parsed Section body."""
    file_content = build_skill_file(name, tags, extra_fm_lines, preamble, headings)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(file_content)
        skill_file = Path(f.name)

    try:
        parsed_name, parsed_tags, sections = parse_skill_file(skill_file)

        # Extract the raw frontmatter lines (between --- markers)
        fm_content = get_frontmatter_content(file_content)
        assume(fm_content.strip() != "")

        # Each non-empty frontmatter line must not appear in any section body
        fm_lines = [line.strip() for line in fm_content.split("\n") if line.strip()]
        for section in sections:
            for fm_line in fm_lines:
                assert fm_line not in section.body, (
                    f"Frontmatter line {fm_line!r} found in section body "
                    f"(heading={section.heading!r})"
                )
    finally:
        skill_file.unlink(missing_ok=True)


@settings(max_examples=100)
@given(
    name=name_strategy,
    tags=tag_strategy,
    extra_fm_lines=st.lists(extra_fm_line_strategy, min_size=0, max_size=3),
    preamble=preamble_strategy,
    headings=st.lists(
        st.tuples(heading_text_strategy, st.lists(section_body_line, min_size=1, max_size=3)),
        min_size=1,
        max_size=3,
    ),
)
def test_preamble_captured_with_headings(name, tags, extra_fm_lines, preamble, headings):
    """Content between closing `---` and first `## ` heading SHALL be captured as a
    preamble Section (with is_preamble=True)."""
    file_content = build_skill_file(name, tags, extra_fm_lines, preamble, headings)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(file_content)
        skill_file = Path(f.name)

    try:
        parsed_name, parsed_tags, sections = parse_skill_file(skill_file)

        # With headings present, there should be a preamble section
        preamble_sections = [s for s in sections if s.is_preamble]
        assert len(preamble_sections) == 1, (
            f"Expected exactly 1 preamble section, got {len(preamble_sections)}"
        )

        preamble_section = preamble_sections[0]
        assert preamble_section.is_preamble is True

        # The preamble body should contain the preamble text content
        # (stripped of leading/trailing whitespace)
        assert preamble.strip() in preamble_section.body, (
            f"Preamble content not found in preamble section body.\n"
            f"Expected to contain: {preamble.strip()!r}\n"
            f"Got body: {preamble_section.body!r}"
        )
    finally:
        skill_file.unlink(missing_ok=True)


@settings(max_examples=100)
@given(
    name=name_strategy,
    tags=tag_strategy,
    extra_fm_lines=st.lists(extra_fm_line_strategy, min_size=0, max_size=3),
    preamble=preamble_strategy,
)
def test_preamble_captured_without_headings(name, tags, extra_fm_lines, preamble):
    """When no ## headings exist, the entire content after frontmatter SHALL be a
    single preamble Section."""
    file_content = build_skill_file(name, tags, extra_fm_lines, preamble, headings=[])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(file_content)
        skill_file = Path(f.name)

    try:
        parsed_name, parsed_tags, sections = parse_skill_file(skill_file)

        # Should be exactly one section marked as preamble
        assert len(sections) == 1, f"Expected 1 section, got {len(sections)}"
        assert sections[0].is_preamble is True

        # That section body should contain the preamble text
        assert preamble.strip() in sections[0].body, (
            f"Preamble content not found in single preamble section.\n"
            f"Expected to contain: {preamble.strip()!r}\n"
            f"Got body: {sections[0].body!r}"
        )
    finally:
        skill_file.unlink(missing_ok=True)


@settings(max_examples=100)
@given(
    name=name_strategy,
    tags=tag_strategy,
    extra_fm_lines=st.lists(extra_fm_line_strategy, min_size=0, max_size=3),
    preamble=preamble_strategy,
    headings=st.lists(
        st.tuples(heading_text_strategy, st.lists(section_body_line, min_size=1, max_size=3)),
        min_size=0,
        max_size=3,
    ),
)
def test_frontmatter_name_and_tags_extracted(name, tags, extra_fm_lines, preamble, headings):
    """The returned name matches what was in the frontmatter, and tags match."""
    file_content = build_skill_file(name, tags, extra_fm_lines, preamble, headings)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(file_content)
        skill_file = Path(f.name)

    try:
        parsed_name, parsed_tags, sections = parse_skill_file(skill_file)

        assert parsed_name == name, (
            f"Parsed name {parsed_name!r} does not match frontmatter name {name!r}"
        )
        assert parsed_tags == tags, (
            f"Parsed tags {parsed_tags!r} do not match frontmatter tags {tags!r}"
        )
    finally:
        skill_file.unlink(missing_ok=True)
