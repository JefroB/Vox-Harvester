# Feature: subagent-improvements, Property 18: Scope Enforcement in Patch Mode
"""Property test: For any set of edit operations and a scope definition (list of
symbol names and/or line ranges), an edit shall be allowed if and only if its target
location (the line range where old_text is found, or the symbol it modifies) overlaps
with at least one scope entry. Edits not overlapping any scope entry shall be rejected.

**Validates: Requirements 7.3**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from local_coder.patch_mode import EditOperation
from local_coder.scope_enforcer import ScopeEntry, validate_edits_against_scope


# --- Strategies ---

def _build_file_content(lines: list[str]) -> str:
    """Join lines into file content with newlines."""
    return "\n".join(lines) + "\n"


@st.composite
def file_with_known_lines(draw: st.DrawFn) -> tuple[str, list[str]]:
    """Generate file content with a known list of distinct lines.

    Returns (file_content, lines) where each line is unique and non-empty.
    """
    num_lines = draw(st.integers(min_value=5, max_value=30))
    lines = []
    for i in range(num_lines):
        # Use index prefix to guarantee uniqueness
        suffix = draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122),
            min_size=1,
            max_size=20,
        ))
        lines.append(f"line_{i}_{suffix}")
    content = _build_file_content(lines)
    return content, lines


@st.composite
def scope_with_line_ranges(draw: st.DrawFn, max_line: int) -> list[ScopeEntry]:
    """Generate a list of line-range scope entries within [1, max_line]."""
    num_entries = draw(st.integers(min_value=1, max_value=3))
    entries = []
    for _ in range(num_entries):
        start = draw(st.integers(min_value=1, max_value=max_line))
        end = draw(st.integers(min_value=start, max_value=max_line))
        entries.append(ScopeEntry(
            kind="line_range",
            value=f"{start}-{end}",
            start_line=start,
            end_line=end,
        ))
    return entries


@st.composite
def edit_targeting_line(draw: st.DrawFn, lines: list[str], target_line_idx: int) -> EditOperation:
    """Create an edit operation whose old_text is exactly lines[target_line_idx]."""
    old_text = lines[target_line_idx]
    new_text = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122),
        min_size=1,
        max_size=20,
    ))
    idx = draw(st.integers(min_value=0, max_value=100))
    return EditOperation(old_text=old_text, new_text=f"replaced_{new_text}", index=idx)


# --- Property Tests ---


@settings(max_examples=100)
@given(data=st.data())
def test_edit_within_scope_line_range_is_allowed(data: st.DataObject) -> None:
    """An edit targeting a line that overlaps with a scope line range is allowed."""
    file_content, lines = data.draw(file_with_known_lines())
    num_lines = len(lines)

    # Pick a scope range
    scope_start = data.draw(st.integers(min_value=1, max_value=num_lines))
    scope_end = data.draw(st.integers(min_value=scope_start, max_value=num_lines))

    scope = [ScopeEntry(
        kind="line_range",
        value=f"{scope_start}-{scope_end}",
        start_line=scope_start,
        end_line=scope_end,
    )]

    # Pick a target line within scope (1-based line numbers, list is 0-based)
    target_idx = data.draw(st.integers(min_value=scope_start - 1, max_value=scope_end - 1))
    op = data.draw(edit_targeting_line(lines, target_idx))

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 1, (
        f"Expected edit at line {target_idx + 1} to be allowed "
        f"(scope {scope_start}-{scope_end}), but it was rejected"
    )
    assert len(rejected) == 0


@settings(max_examples=100)
@given(data=st.data())
def test_edit_outside_scope_line_range_is_rejected(data: st.DataObject) -> None:
    """An edit targeting a line outside all scope line ranges is rejected."""
    file_content, lines = data.draw(file_with_known_lines())
    num_lines = len(lines)
    assume(num_lines >= 5)

    # Create a scope that covers only part of the file
    scope_start = data.draw(st.integers(min_value=1, max_value=num_lines // 2))
    scope_end = data.draw(st.integers(min_value=scope_start, max_value=num_lines // 2))

    scope = [ScopeEntry(
        kind="line_range",
        value=f"{scope_start}-{scope_end}",
        start_line=scope_start,
        end_line=scope_end,
    )]

    # Pick a target line clearly outside scope (after scope_end)
    # Lines are 1-based: scope_end+1 to num_lines are outside
    assume(scope_end < num_lines)
    target_idx = data.draw(st.integers(min_value=scope_end, max_value=num_lines - 1))
    # target_idx is 0-based, line number is target_idx + 1
    # Ensure it's truly outside scope
    assume(target_idx + 1 > scope_end)

    op = data.draw(edit_targeting_line(lines, target_idx))

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(rejected) == 1, (
        f"Expected edit at line {target_idx + 1} to be rejected "
        f"(scope {scope_start}-{scope_end}), but it was allowed"
    )
    assert len(allowed) == 0


@settings(max_examples=100)
@given(data=st.data())
def test_edit_matching_symbol_scope_is_allowed(data: st.DataObject) -> None:
    """An edit whose old_text contains a declared symbol name is allowed."""
    # Generate a symbol name
    symbol_name = data.draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{2,10}", fullmatch=True))

    # Build file content that contains the symbol
    prefix_lines = data.draw(st.integers(min_value=0, max_value=5))
    lines = [f"prefix_line_{i}" for i in range(prefix_lines)]
    lines.append(f"def {symbol_name}():")
    lines.append(f"    return '{symbol_name}_result'")
    suffix_lines = data.draw(st.integers(min_value=0, max_value=5))
    lines.extend([f"suffix_line_{i}" for i in range(suffix_lines)])

    file_content = _build_file_content(lines)

    # Create an edit whose old_text contains the symbol name
    old_text = f"def {symbol_name}():"
    op = EditOperation(old_text=old_text, new_text=f"def {symbol_name}(x):", index=0)

    scope = [ScopeEntry(kind="symbol", value=symbol_name)]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(allowed) == 1, (
        f"Expected edit containing symbol '{symbol_name}' to be allowed"
    )
    assert len(rejected) == 0


@settings(max_examples=100)
@given(data=st.data())
def test_edit_not_matching_symbol_and_no_line_overlap_is_rejected(data: st.DataObject) -> None:
    """An edit that doesn't contain the symbol and isn't in a line-range scope is rejected."""
    # Generate two distinct symbol names
    symbol_a = data.draw(st.from_regex(r"[a-z][a-z0-9]{3,8}", fullmatch=True))
    symbol_b = data.draw(st.from_regex(r"[A-Z][A-Za-z0-9]{3,8}", fullmatch=True))
    # Ensure they're distinct
    assume(symbol_a not in symbol_b and symbol_b not in symbol_a)

    # File contains both symbols
    lines = [
        f"def {symbol_a}():",
        f"    return '{symbol_a}'",
        f"def {symbol_b}():",
        f"    return '{symbol_b}'",
    ]
    file_content = _build_file_content(lines)

    # Edit targets symbol_b but scope only allows symbol_a
    old_text = f"def {symbol_b}():"
    assume(symbol_a not in old_text)

    op = EditOperation(old_text=old_text, new_text=f"def {symbol_b}(x):", index=0)
    scope = [ScopeEntry(kind="symbol", value=symbol_a)]

    allowed, rejected = validate_edits_against_scope([op], scope, file_content)

    assert len(rejected) == 1, (
        f"Expected edit targeting '{symbol_b}' to be rejected "
        f"when scope is '{symbol_a}'"
    )
    assert len(allowed) == 0


@settings(max_examples=100)
@given(data=st.data())
def test_mixed_edits_partitioned_by_scope(data: st.DataObject) -> None:
    """Multiple edits are correctly partitioned: in-scope allowed, out-of-scope rejected."""
    # Build a file with enough lines
    num_lines = data.draw(st.integers(min_value=10, max_value=20))
    lines = [f"content_line_{i}" for i in range(num_lines)]
    file_content = _build_file_content(lines)

    # Scope covers lines [scope_start, scope_end] (1-based)
    scope_start = data.draw(st.integers(min_value=1, max_value=num_lines // 3))
    scope_end = data.draw(st.integers(min_value=scope_start, max_value=(2 * num_lines) // 3))
    assume(scope_end < num_lines)  # Ensure there are lines outside scope

    scope = [ScopeEntry(
        kind="line_range",
        value=f"{scope_start}-{scope_end}",
        start_line=scope_start,
        end_line=scope_end,
    )]

    # Create some edits inside scope and some outside
    in_scope_count = data.draw(st.integers(min_value=1, max_value=3))
    out_scope_count = data.draw(st.integers(min_value=1, max_value=3))

    ops = []
    expected_allowed_indices = set()
    expected_rejected_indices = set()

    # In-scope edits (target lines within scope range)
    for i in range(in_scope_count):
        target_idx = data.draw(st.integers(min_value=scope_start - 1, max_value=scope_end - 1))
        op = EditOperation(
            old_text=lines[target_idx],
            new_text=f"modified_in_{i}",
            index=i,
        )
        ops.append(op)
        expected_allowed_indices.add(i)

    # Out-of-scope edits (target lines after scope_end)
    for i in range(out_scope_count):
        target_idx = data.draw(st.integers(min_value=scope_end, max_value=num_lines - 1))
        # Verify it's truly outside
        assume(target_idx + 1 > scope_end)
        op_idx = in_scope_count + i
        op = EditOperation(
            old_text=lines[target_idx],
            new_text=f"modified_out_{i}",
            index=op_idx,
        )
        ops.append(op)
        expected_rejected_indices.add(op_idx)

    allowed, rejected = validate_edits_against_scope(ops, scope, file_content)

    allowed_indices = {op.index for op in allowed}
    rejected_indices = {op.index for op in rejected}

    assert allowed_indices == expected_allowed_indices, (
        f"Allowed mismatch: got {allowed_indices}, expected {expected_allowed_indices}"
    )
    assert rejected_indices == expected_rejected_indices, (
        f"Rejected mismatch: got {rejected_indices}, expected {expected_rejected_indices}"
    )
