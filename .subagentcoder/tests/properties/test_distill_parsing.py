# Feature: skill-distillation, Property 9: Section parsing splits only on ## outside code fences
"""Property-based tests for section parsing behavior.

**Validates: Requirements 7.1, 7.4, 7.5**

For any markdown document, the parser SHALL produce one Section per `## ` heading
that appears outside fenced code blocks (triple-backtick regions). Lines matching
`## ` inside fenced code blocks SHALL NOT create section boundaries. Sub-headings
(`###`, `####`, etc.) SHALL remain part of their parent section. If no `## `
headings exist, the entire document SHALL be treated as one section.
"""

import sys
import tempfile
from pathlib import Path

# Make distiller importable from .kiro/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / ".kiro" / "scripts"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from distiller import parse_skill_file, Section


# --- Strategies ---

# Generate simple identifiers for headings (no newlines, non-empty, no surrogates)
heading_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        whitelist_characters="-_",
        blacklist_characters="#",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Generate body text lines (no triple backticks, no ## at start of line, no surrogates)
safe_body_line = st.text(
    alphabet=st.characters(blacklist_characters="\r\n`", blacklist_categories=("Cs",)),
    min_size=0,
    max_size=60,
).filter(lambda s: not s.startswith("## ") and not s.startswith("```"))

# Generate lines that could appear inside code fences (including ## headings)
fence_content_line = st.text(
    alphabet=st.characters(blacklist_characters="\r\n`", blacklist_categories=("Cs",)),
    min_size=0,
    max_size=60,
)

# Generate a code fence language tag
fence_language = st.sampled_from(["", "python", "markdown", "javascript", "yaml", "text"])


@st.composite
def markdown_document(draw):
    """Generate a markdown document with a mix of headings, body, sub-headings, and code fences.

    Returns (document_text, expected_h2_count_outside_fences).
    """
    # Optional frontmatter
    has_frontmatter = draw(st.booleans())
    name = draw(heading_text) if has_frontmatter else ""

    # Number of top-level sections (## headings outside fences)
    num_h2_headings = draw(st.integers(min_value=0, max_value=5))

    # Build document parts
    parts = []

    if has_frontmatter:
        parts.append("---")
        parts.append(f"name: {name}")
        parts.append("tags: [code]")
        parts.append("---")
        parts.append("")

    # Optional preamble (text before first ## heading)
    has_preamble = draw(st.booleans())
    if has_preamble:
        preamble_lines = draw(st.lists(safe_body_line, min_size=1, max_size=3))
        parts.extend(preamble_lines)
        parts.append("")

    # Generate sections with ## headings
    for i in range(num_h2_headings):
        h2_text = draw(heading_text)
        parts.append(f"## {h2_text}")
        parts.append("")

        # Body lines for this section
        body_lines = draw(st.lists(safe_body_line, min_size=0, max_size=4))
        parts.extend(body_lines)

        # Optionally add sub-headings (### or ####) - these should NOT create new sections
        num_sub_headings = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_sub_headings):
            sub_level = draw(st.sampled_from(["###", "####"]))
            sub_text = draw(heading_text)
            parts.append(f"{sub_level} {sub_text}")
            sub_body = draw(st.lists(safe_body_line, min_size=0, max_size=2))
            parts.extend(sub_body)

        # Optionally add a code fence that may contain ## headings
        has_fence = draw(st.booleans())
        if has_fence:
            lang = draw(fence_language)
            parts.append(f"```{lang}")
            # Put some lines inside the fence, including potential ## headings
            num_fence_lines = draw(st.integers(min_value=1, max_value=4))
            for _ in range(num_fence_lines):
                # Intentionally include ## headings inside fences
                include_fake_heading = draw(st.booleans())
                if include_fake_heading:
                    fake_h2 = draw(heading_text)
                    parts.append(f"## {fake_h2}")
                else:
                    parts.append(draw(fence_content_line))
            parts.append("```")
            parts.append("")

    document = "\n".join(parts)
    return (document, num_h2_headings, has_frontmatter, name)


@st.composite
def document_with_fenced_headings_only(draw):
    """Generate a document where ALL ## headings are inside code fences (none outside).

    This should result in a single section.
    """
    has_frontmatter = draw(st.booleans())
    name = draw(heading_text) if has_frontmatter else ""

    parts = []
    if has_frontmatter:
        parts.append("---")
        parts.append(f"name: {name}")
        parts.append("tags: [test]")
        parts.append("---")
        parts.append("")

    # Some body text
    body_lines = draw(st.lists(safe_body_line, min_size=1, max_size=3))
    parts.extend(body_lines)
    parts.append("")

    # Code fences with ## headings inside
    num_fences = draw(st.integers(min_value=1, max_value=3))
    for _ in range(num_fences):
        lang = draw(fence_language)
        parts.append(f"```{lang}")
        num_fake_headings = draw(st.integers(min_value=1, max_value=3))
        for _ in range(num_fake_headings):
            fake_h2 = draw(heading_text)
            parts.append(f"## {fake_h2}")
        parts.append("```")
        parts.append("")

    document = "\n".join(parts)
    return (document, name, has_frontmatter)


# --- Helper ---

def _write_and_parse(content: str) -> list[Section]:
    """Write content to a temp file and parse it, returning sections."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        file_path = Path(f.name)
    try:
        _, _, sections = parse_skill_file(file_path)
        return sections
    finally:
        file_path.unlink(missing_ok=True)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=markdown_document())
def test_section_count_matches_h2_headings_outside_fences(data):
    """The number of non-preamble sections equals the number of ## headings outside code fences."""
    document, expected_h2_count, has_frontmatter, name = data

    sections = _write_and_parse(document)

    # Count non-preamble sections
    non_preamble = [s for s in sections if not s.is_preamble]
    assert len(non_preamble) == expected_h2_count


@settings(max_examples=100)
@given(data=document_with_fenced_headings_only())
def test_headings_inside_fences_do_not_create_sections(data):
    """Lines starting with ## inside code fences do NOT create section boundaries."""
    document, name, has_frontmatter = data

    sections = _write_and_parse(document)

    # All ## headings are inside fences, so there should be no non-preamble sections
    non_preamble = [s for s in sections if not s.is_preamble]
    assert len(non_preamble) == 0

    # The entire document should be treated as one section (preamble)
    assert len(sections) == 1
    assert sections[0].is_preamble is True


@settings(max_examples=100)
@given(data=markdown_document())
def test_sub_headings_remain_in_parent_section(data):
    """Sub-headings (###, ####) appear in the body of their parent section, not as separate sections."""
    document, expected_h2_count, has_frontmatter, name = data

    sections = _write_and_parse(document)

    # No section heading should start with ### or ####
    for section in sections:
        if not section.is_preamble:
            # The heading field should not contain ### or #### prefixed text
            assert not section.heading.startswith("#"), (
                f"Sub-heading leaked as section: '{section.heading}'"
            )


@settings(max_examples=100)
@given(data=markdown_document())
def test_no_h2_headings_means_single_section(data):
    """If no ## headings exist outside fences, result has exactly one section."""
    document, expected_h2_count, has_frontmatter, name = data
    assume(expected_h2_count == 0)

    sections = _write_and_parse(document)
    assert len(sections) == 1
    assert sections[0].is_preamble is True
