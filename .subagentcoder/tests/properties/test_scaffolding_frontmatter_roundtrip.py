# Feature: scaffolding-library, Property 1: Frontmatter Round-Trip
"""Property-based tests for frontmatter round-trip parsing.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

For any valid frontmatter dictionary containing name (string), tags (list of
strings), category (string), complexity (one of "simple", "complex", "any"),
description (string), and priority (integer), serializing it to YAML frontmatter
format and parsing it back with _parse_template_frontmatter should produce an
equivalent dictionary.
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scaffolding_selector import _parse_template_frontmatter


# --- Strategies ---

# Safe alphabet for YAML values: letters and digits only to avoid YAML special chars
# (colons, quotes, brackets, pipes, hashes, etc. can break YAML parsing)
_yaml_safe_alphabet = st.characters(
    whitelist_categories=("L", "N"),
)

# Non-empty name string (YAML-safe)
name_strategy = st.text(
    alphabet=_yaml_safe_alphabet,
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# Non-empty tag string (YAML-safe, no spaces to avoid YAML list parsing issues)
tag_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() != "")

# Tags: non-empty list of non-empty strings
tags_strategy = st.lists(tag_strategy, min_size=1, max_size=5)

# Category: non-empty string (YAML-safe)
category_strategy = st.text(
    alphabet=_yaml_safe_alphabet,
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() != "")

# Complexity: one of the three valid values
complexity_strategy = st.sampled_from(["simple", "complex", "any"])

# Description: non-empty string (YAML-safe)
description_strategy = st.text(
    alphabet=_yaml_safe_alphabet,
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# Priority: integer
priority_strategy = st.integers(min_value=-100, max_value=100)


# --- Helpers ---

def serialize_frontmatter(
    name: str,
    tags: list[str],
    category: str,
    complexity: str,
    description: str,
    priority: int,
) -> str:
    """Serialize a frontmatter dict to YAML frontmatter format with body text.

    Uses explicit YAML quoting to ensure values are parsed correctly.
    """
    lines = []
    lines.append("---")
    lines.append(f"name: \"{name}\"")
    # Format tags as YAML list
    tags_formatted = ", ".join(f"\"{t}\"" for t in tags)
    lines.append(f"tags: [{tags_formatted}]")
    lines.append(f"category: \"{category}\"")
    lines.append(f"complexity: \"{complexity}\"")
    lines.append(f"description: \"{description}\"")
    lines.append(f"priority: {priority}")
    lines.append("---")
    lines.append("")
    lines.append("Template body content goes here.")
    return "\n".join(lines)


# --- Property Tests ---


@settings(max_examples=100)
@given(
    name=name_strategy,
    tags=tags_strategy,
    category=category_strategy,
    complexity=complexity_strategy,
    description=description_strategy,
    priority=priority_strategy,
)
def test_frontmatter_round_trip(name, tags, category, complexity, description, priority):
    """Serializing a valid frontmatter dict and parsing it back produces equivalent values.

    This validates that _parse_template_frontmatter correctly extracts all fields
    from well-formed YAML frontmatter: name, tags, category, complexity, description,
    and priority.
    """
    content = serialize_frontmatter(name, tags, category, complexity, description, priority)

    # Write to a temporary file and parse
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    ) as f:
        f.write(content)
        filepath = Path(f.name)

    try:
        result = _parse_template_frontmatter(filepath)

        # Must not return None for valid frontmatter
        assert result is not None, (
            f"_parse_template_frontmatter returned None for valid frontmatter.\n"
            f"Content:\n{content}"
        )

        # Verify each field round-trips correctly
        assert result["name"] == name, (
            f"Name mismatch: expected {name!r}, got {result['name']!r}"
        )
        assert result["tags"] == tags, (
            f"Tags mismatch: expected {tags!r}, got {result['tags']!r}"
        )
        assert result["category"] == category, (
            f"Category mismatch: expected {category!r}, got {result['category']!r}"
        )
        assert result["complexity"] == complexity, (
            f"Complexity mismatch: expected {complexity!r}, got {result['complexity']!r}"
        )
        assert result["description"] == description, (
            f"Description mismatch: expected {description!r}, got {result['description']!r}"
        )
        assert result["priority"] == priority, (
            f"Priority mismatch: expected {priority!r}, got {result['priority']!r}"
        )
    finally:
        filepath.unlink(missing_ok=True)
