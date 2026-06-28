# Feature: scaffolding-library, Property 2: Malformed Frontmatter Robustness
"""Property-based tests for malformed frontmatter robustness.

**Validates: Requirements 2.8, 10.5**

For any string content that does not constitute valid YAML frontmatter
(random bytes, missing delimiters, partial YAML, non-YAML text between
``---`` markers), calling ``_parse_template_frontmatter`` SHALL not raise
an exception and SHALL return either a partial metadata dict or None.
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.scaffolding_selector import _parse_template_frontmatter


# --- Strategies ---

# Arbitrary text content (no constraints)
arbitrary_text_strategy = st.text(min_size=0, max_size=500)

# Binary content decoded as UTF-8 with replacement characters
binary_as_text_strategy = st.binary(min_size=0, max_size=500).map(
    lambda b: b.decode("utf-8", errors="replace")
)

# Partial YAML: starts with --- but has random content after
partial_yaml_strategy = st.tuples(
    st.just("---\n"),
    st.text(min_size=0, max_size=300),
).map(lambda parts: parts[0] + parts[1])

# Content between --- markers with non-YAML text
non_yaml_between_delimiters_strategy = st.tuples(
    st.just("---\n"),
    st.text(min_size=1, max_size=200).filter(lambda s: "---" not in s),
    st.just("\n---\n"),
    st.text(min_size=0, max_size=100),
).map(lambda parts: parts[0] + parts[1] + parts[2] + parts[3])


# --- Helpers ---

def write_temp_file(content: str) -> Path:
    """Write content to a temporary file and return its Path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)


def assert_valid_return(result):
    """Assert the return value is either None or a dict."""
    assert result is None or isinstance(result, dict), (
        f"Expected None or dict, got {type(result).__name__}: {result!r}"
    )


# --- Property Tests ---


@settings(max_examples=100)
@given(content=arbitrary_text_strategy)
def test_arbitrary_text_never_crashes(content):
    """_parse_template_frontmatter never raises on arbitrary text content."""
    filepath = write_temp_file(content)
    try:
        result = _parse_template_frontmatter(filepath)
        assert_valid_return(result)
    finally:
        filepath.unlink(missing_ok=True)


@settings(max_examples=100)
@given(content=binary_as_text_strategy)
def test_binary_content_never_crashes(content):
    """_parse_template_frontmatter never raises on binary-derived content."""
    filepath = write_temp_file(content)
    try:
        result = _parse_template_frontmatter(filepath)
        assert_valid_return(result)
    finally:
        filepath.unlink(missing_ok=True)


@settings(max_examples=100)
@given(content=partial_yaml_strategy)
def test_partial_yaml_never_crashes(content):
    """_parse_template_frontmatter never raises on content starting with ---
    but having random content after (missing closing delimiter or invalid YAML)."""
    filepath = write_temp_file(content)
    try:
        result = _parse_template_frontmatter(filepath)
        assert_valid_return(result)
    finally:
        filepath.unlink(missing_ok=True)


@settings(max_examples=100)
@given(content=non_yaml_between_delimiters_strategy)
def test_non_yaml_between_delimiters_never_crashes(content):
    """_parse_template_frontmatter never raises when non-YAML text appears
    between valid --- delimiters."""
    filepath = write_temp_file(content)
    try:
        result = _parse_template_frontmatter(filepath)
        assert_valid_return(result)
    finally:
        filepath.unlink(missing_ok=True)
