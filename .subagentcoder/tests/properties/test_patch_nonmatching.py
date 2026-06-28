# Feature: subagent-improvements, Property 14: Patch Application — Non-Matching Edits Skipped
"""Property-based tests for non-matching edit operations being skipped.

**Validates: Requirements 6.4**

For any file content and any edit operation whose `old_text` does not appear
anywhere in the current file content, that operation shall be skipped without
modifying the file, and the count of skipped operations shall increment.
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.patch_mode import apply_edit_operations, EditOperation


# --- Strategies ---

# Generate arbitrary file content (non-empty to have a meaningful file).
# Exclude surrogates (Cs) and bare \r to avoid text-mode newline translation
# issues on Windows (Python's text mode normalizes \r\n and \r to \n on read).
file_content_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r"),
    min_size=1,
    max_size=500,
)

# Generate old_text that we will ensure does NOT appear in the file
non_matching_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r"),
    min_size=1,
    max_size=100,
)

# Generate replacement text (can be anything, same constraints for consistency)
new_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r"),
    min_size=0,
    max_size=100,
)


@st.composite
def non_matching_edit_operations(draw):
    """Generate file content and a list of edit operations whose old_text values
    are guaranteed not to appear in the file content.

    Returns (file_content, operations) where each operation's old_text is absent
    from file_content.
    """
    content = draw(file_content_strategy)
    num_ops = draw(st.integers(min_value=1, max_value=5))

    operations = []
    for i in range(num_ops):
        old_text = draw(non_matching_text_strategy)
        # Ensure old_text does NOT appear in the content
        assume(old_text not in content)
        new_text = draw(new_text_strategy)
        operations.append(EditOperation(old_text=old_text, new_text=new_text, index=i))

    return content, operations


# --- Property Tests ---


@settings(max_examples=100)
@given(data=non_matching_edit_operations())
def test_non_matching_edits_are_skipped(data):
    """Non-matching edit operations are skipped and file content is unchanged.

    When old_text does not appear in the file, the operation is skipped,
    applied_count is 0, and skipped_count equals the number of operations.
    """
    content, operations = data

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(content)
        test_file = Path(f.name)

    try:
        # Apply non-matching operations
        applied, skipped = apply_edit_operations(test_file, operations)

        # All operations should be skipped
        assert applied == 0, f"Expected 0 applied, got {applied}"
        assert skipped == len(operations), (
            f"Expected {len(operations)} skipped, got {skipped}"
        )

        # File content must be unchanged
        result_content = test_file.read_text(encoding="utf-8")
        assert result_content == content, "File content should not be modified"
    finally:
        test_file.unlink(missing_ok=True)


@settings(max_examples=100)
@given(data=non_matching_edit_operations())
def test_skipped_count_increments_per_operation(data):
    """The skipped count equals the total number of non-matching operations.

    Each non-matching operation increments the skip counter by exactly 1.
    """
    content, operations = data

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(content)
        test_file = Path(f.name)

    try:
        applied, skipped = apply_edit_operations(test_file, operations)

        # skipped_count must match the exact number of operations provided
        assert skipped == len(operations)
        # applied_count must be zero since none match
        assert applied == 0
    finally:
        test_file.unlink(missing_ok=True)
