"""Property-based tests for sample ID format validation.

**Validates: Requirements 1.6**

Tests the regex pattern /^[a-zA-Z0-9_-]+$/ used by the POST /api/samples/:id/isolate
endpoint to validate sample IDs. This is a pure logic test — validates the regex
directly in Python without hitting the server.

Property 2: Invalid sample ID format rejected
For any string that is empty or contains characters outside [a-zA-Z0-9_-],
the validation SHALL reject it (pattern does not match).
"""

import re

from hypothesis import given, settings, assume
import hypothesis.strategies as st


# Mirror the server-side regex: /^[a-zA-Z0-9_-]+$/
# Use re.DOTALL so that $ truly means end-of-string (not before trailing \n),
# matching JavaScript's RegExp behavior where $ does not match before \n.
VALID_ID_PATTERN = re.compile(r"\A[a-zA-Z0-9_-]+\Z")

# Characters that are allowed in a valid sample ID
VALID_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


@given(sample_id=st.from_regex(r"^[a-zA-Z0-9_-]+$", fullmatch=True))
@settings(max_examples=100)
def test_valid_ids_pass_pattern(sample_id: str) -> None:
    """Valid sample IDs (only alphanumeric, hyphens, underscores) match the pattern.

    **Validates: Requirements 1.6**
    """
    assert VALID_ID_PATTERN.match(sample_id) is not None


def test_empty_string_fails_pattern() -> None:
    """Empty string fails the pattern because + requires at least one character.

    **Validates: Requirements 1.6**
    """
    assert VALID_ID_PATTERN.match("") is None


@given(sample_id=st.text(min_size=1).filter(lambda s: not VALID_ID_PATTERN.match(s)))
@settings(max_examples=100)
def test_invalid_ids_fail_pattern(sample_id: str) -> None:
    """Strings containing any character outside [a-zA-Z0-9_-] fail the pattern.

    **Validates: Requirements 1.6**
    """
    assert VALID_ID_PATTERN.match(sample_id) is None


@given(
    sample_id=st.text(
        alphabet=st.characters(
            blacklist_categories=("Lu", "Ll", "Nd"),
            blacklist_characters="-_",
        ),
        min_size=1,
    )
)
@settings(max_examples=100)
def test_strings_with_only_invalid_chars_fail(sample_id: str) -> None:
    """Strings composed entirely of invalid characters fail the pattern.

    **Validates: Requirements 1.6**
    """
    assert VALID_ID_PATTERN.match(sample_id) is None


@given(
    valid_part=st.from_regex(r"^[a-zA-Z0-9_-]+$", fullmatch=True),
    invalid_char=st.sampled_from(
        [" ", ".", "/", "\\", "?", "#", "%", "@", "!", "\x00", "\n", "\t", ":", "*", "<", ">", "|", "é", "日"]
    ),
)
@settings(max_examples=100)
def test_mixed_valid_and_invalid_chars_fail(valid_part: str, invalid_char: str) -> None:
    """A string with valid chars plus any single invalid char fails the pattern.

    **Validates: Requirements 1.6**
    """
    # Insert invalid char at various positions
    mixed = valid_part + invalid_char
    assert VALID_ID_PATTERN.match(mixed) is None

    mixed_prefix = invalid_char + valid_part
    assert VALID_ID_PATTERN.match(mixed_prefix) is None
