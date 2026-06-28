"""Smoke tests for validate_edits_against_scope()."""

import sys

from local_coder.patch_mode import EditOperation
from local_coder.scope_enforcer import (
    ScopeEntry,
    parse_scope,
    validate_edits_against_scope,
)


def test_edit_within_line_range_is_allowed():
    """An edit whose old_text falls within a declared line range scope is allowed."""
    file_content = "line1\nline2\nline3\nline4\nline5\n"
    # old_text "line3" is on line 3 (1-based)
    op = EditOperation(old_text="line3", new_text="LINE3", index=0)
    scope = [ScopeEntry(kind="line_range", value="2-4", start_line=2, end_line=4)]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 1
    assert len(rejected) == 0
    assert allowed[0] is op


def test_edit_outside_line_range_is_rejected():
    """An edit whose old_text is outside the declared line range scope is rejected."""
    file_content = "line1\nline2\nline3\nline4\nline5\n"
    # old_text "line5" is on line 5, scope is lines 1-3
    op = EditOperation(old_text="line5", new_text="LINE5", index=0)
    scope = [ScopeEntry(kind="line_range", value="1-3", start_line=1, end_line=3)]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 0
    assert len(rejected) == 1
    assert rejected[0] is op


def test_edit_matching_symbol_name_is_allowed():
    """An edit whose old_text contains the symbol name is allowed."""
    file_content = "def validate_email(addr):\n    return '@' in addr\n"
    op = EditOperation(
        old_text="def validate_email(addr):\n    return '@' in addr",
        new_text="def validate_email(addr):\n    return bool(re.match(r'.+@.+', addr))",
        index=0,
    )
    scope = [ScopeEntry(kind="symbol", value="validate_email")]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 1
    assert len(rejected) == 0


def test_edit_not_matching_symbol_is_rejected():
    """An edit whose old_text does NOT contain the symbol name is rejected."""
    file_content = "def other_func():\n    pass\ndef validate_email():\n    pass\n"
    # The edit targets 'other_func' but scope only allows 'validate_email'
    op = EditOperation(old_text="def other_func():\n    pass", new_text="def other_func():\n    return 1", index=0)
    scope = [ScopeEntry(kind="symbol", value="validate_email")]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 0
    assert len(rejected) == 1


def test_description_scope_always_allows():
    """A natural-language description scope entry always allows any edit."""
    file_content = "anything here\n"
    op = EditOperation(old_text="anything here", new_text="replaced", index=0)
    scope = [ScopeEntry(kind="description", value="the error handling section")]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 1
    assert len(rejected) == 0


def test_old_text_not_found_is_rejected():
    """An edit whose old_text is not found in file_content is rejected."""
    file_content = "some content\n"
    op = EditOperation(old_text="nonexistent text", new_text="replacement", index=0)
    scope = [ScopeEntry(kind="line_range", value="1-10", start_line=1, end_line=10)]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 0
    assert len(rejected) == 1


def test_multiple_edits_partitioned_correctly():
    """Multiple edits are correctly partitioned into allowed and rejected."""
    file_content = "line1\nline2\nline3\nline4\nline5\n"
    ops = [
        EditOperation(old_text="line2", new_text="LINE2", index=0),  # line 2 - in scope
        EditOperation(old_text="line5", new_text="LINE5", index=1),  # line 5 - out of scope
        EditOperation(old_text="line3", new_text="LINE3", index=2),  # line 3 - in scope
    ]
    scope = [ScopeEntry(kind="line_range", value="1-3", start_line=1, end_line=3)]

    allowed, rejected = validate_edits_against_scope(ops, scope, file_content)

    assert len(allowed) == 2
    assert len(rejected) == 1
    assert allowed[0].index == 0
    assert allowed[1].index == 2
    assert rejected[0].index == 1


def test_warning_format_on_rejected_edit(capsys):
    """Rejected edits emit a warning to stderr in the expected format."""
    file_content = "line1\nline2\nline3\n"
    op = EditOperation(old_text="line3", new_text="x", index=0)
    scope = [ScopeEntry(kind="line_range", value="1-1", start_line=1, end_line=1)]

    validate_edits_against_scope([op], scope, file_content)

    captured = capsys.readouterr()
    assert "[WARN] scope: Rejected edit at lines 3-3" in captured.err
    assert 'outside scope "1-1"' in captured.err


def test_integration_with_parse_scope():
    """End-to-end test combining parse_scope with validate_edits_against_scope."""
    file_content = "def foo():\n    pass\ndef bar():\n    pass\n"
    scope = parse_scope("foo, 1-2")

    op_in = EditOperation(old_text="def foo():\n    pass", new_text="def foo():\n    return 1", index=0)
    op_out = EditOperation(old_text="def bar():\n    pass", new_text="def bar():\n    return 2", index=1)

    allowed, rejected = validate_edits_against_scope([op_in, op_out], scope, file_content)

    # op_in contains "foo" (symbol match) and is at lines 1-2 (line range match) → allowed
    # op_out doesn't contain "foo" and is at lines 3-4 (no overlap with 1-2) → rejected
    assert len(allowed) == 1
    assert len(rejected) == 1
    assert allowed[0].index == 0
    assert rejected[0].index == 1
