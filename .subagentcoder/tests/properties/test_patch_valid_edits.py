# Feature: subagent-improvements, Property 13: Patch Application — Valid Edits
"""Property-based tests for patch application with valid edits.

**Validates: Requirements 6.3**

For any file content and any sequence of edit operations where each operation's
`old_text` appears exactly once in the file content (after prior edits have been
applied), applying all operations sequentially shall produce a file where each
`old_text` has been replaced by its corresponding `new_text`.
"""

import sys
import tempfile
from pathlib import Path

# Make local_coder package importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.patch_mode import apply_edit_operations, EditOperation


# --- Strategies ---


def _make_marker(index: int) -> str:
    """Create a unique marker string for a given index."""
    return f"__UNIQUE_MARKER_{index}__"


@st.composite
def valid_file_and_operations(draw):
    """Generate a file with unique markers and edit operations targeting each marker.

    Each marker appears exactly once in the file content. Each edit operation
    replaces one marker with a new_text that does not contain any of the remaining
    markers (to preserve uniqueness after sequential application).
    """
    n_ops = draw(st.integers(min_value=1, max_value=5))

    # Generate unique markers
    markers = [_make_marker(i) for i in range(n_ops)]

    # Build file content with markers interspersed with filler
    parts = []
    for i in range(n_ops):
        filler = draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=0,
            max_size=20,
        ))
        parts.append(filler)
        parts.append(markers[i])
    # Trailing filler
    trailing = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=0,
        max_size=20,
    ))
    parts.append(trailing)
    file_content = "\n".join(parts)

    # Generate replacement texts that don't contain any marker strings
    operations = []
    for i in range(n_ops):
        new_text = draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=1,
            max_size=30,
        ))
        # Ensure new_text doesn't accidentally contain any marker
        assume(all(m not in new_text for m in markers))
        operations.append(EditOperation(old_text=markers[i], new_text=new_text, index=i))

    return file_content, operations


# --- Property Test ---


@settings(max_examples=100)
@given(data=valid_file_and_operations())
def test_valid_edits_replace_all_markers(data):
    """Applying valid edit operations replaces each old_text with new_text.

    After applying all operations:
    - Each old_text (marker) is gone from the file.
    - Each new_text is present in the file.
    """
    file_content, operations = data

    # Write the file content to a temp file (manage lifecycle within the test)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    ) as f:
        f.write(file_content)
        target_file = Path(f.name)

    try:
        # Apply the edit operations
        applied, skipped = apply_edit_operations(target_file, operations)

        # All operations should have been applied (each marker is unique)
        assert applied == len(operations), (
            f"Expected {len(operations)} edits applied, got {applied} applied and {skipped} skipped"
        )
        assert skipped == 0, f"Expected 0 skipped edits, got {skipped}"

        # Read the result
        result = target_file.read_text(encoding="utf-8")

        # Verify: each old_text is gone and each new_text is present
        for op in operations:
            assert op.old_text not in result, (
                f"old_text '{op.old_text}' should have been replaced but is still present"
            )
            assert op.new_text in result, (
                f"new_text '{op.new_text}' should be present after replacement but is missing"
            )
    finally:
        target_file.unlink(missing_ok=True)
