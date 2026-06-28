# Feature: local-coder-workflow-improvements, Property 1: Annotation Format Correctness
"""Property test: For any CodeSearchResult with a file_path and optional (start_line, end_line)
pair, _format_annotation SHALL produce output matching the exact format specification:
- With valid start_line and end_line: '<!-- target: <path> lines: <start>-<end> -->'
- Without line range (None for either): '<!-- target: <path> -->'

**Validates: Requirements 1.1, 1.2, 1.3, 1.6**
"""

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.task_annotator import CodeSearchResult, TaskAnnotator

# Regex patterns for the two valid annotation formats
_ANNOTATION_WITH_LINES = re.compile(
    r"^<!-- target: (.+) lines: (\d+)-(\d+) -->$"
)
_ANNOTATION_WITHOUT_LINES = re.compile(
    r"^<!-- target: (.+) -->$"
)

# Strategy for generating realistic file path segments
_path_segment = st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_\-]*", fullmatch=True)
_file_extension = st.sampled_from([".py", ".ts", ".js", ".rs", ".go", ".java", ".md"])

# Build realistic file paths like 'src/foo/bar.py'
_file_path_strategy = st.builds(
    lambda parts, ext: "/".join(parts) + ext,
    parts=st.lists(_path_segment, min_size=1, max_size=4),
    ext=_file_extension,
)

# Dummy annotator instance (project_root doesn't matter for _format_annotation)
_annotator = TaskAnnotator(project_root=Path("/tmp/dummy_project"))


@settings(max_examples=100)
@given(
    file_path=_file_path_strategy,
    start_line=st.integers(min_value=1, max_value=100_000),
    end_line_offset=st.integers(min_value=0, max_value=1000),
)
def test_annotation_with_lines_matches_exact_format(
    file_path: str, start_line: int, end_line_offset: int
) -> None:
    """When start_line and end_line are both present and valid (start <= end),
    output matches exactly '<!-- target: <path> lines: <start>-<end> -->'."""
    end_line = start_line + end_line_offset  # Guarantees start <= end

    result = CodeSearchResult(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        found=True,
    )

    annotation = _annotator._format_annotation(result)

    # Verify exact format via regex
    match = _ANNOTATION_WITH_LINES.match(annotation)
    assert match is not None, (
        f"Annotation does not match expected format.\n"
        f"  Got:      '{annotation}'\n"
        f"  Expected: '<!-- target: {file_path} lines: {start_line}-{end_line} -->'"
    )

    # Verify extracted values match inputs
    assert match.group(1) == file_path, (
        f"Path mismatch: expected '{file_path}', got '{match.group(1)}'"
    )
    assert int(match.group(2)) == start_line, (
        f"start_line mismatch: expected {start_line}, got {match.group(2)}"
    )
    assert int(match.group(3)) == end_line, (
        f"end_line mismatch: expected {end_line}, got {match.group(3)}"
    )


@settings(max_examples=100)
@given(
    file_path=_file_path_strategy,
    use_none_start=st.booleans(),
    use_none_end=st.booleans(),
)
def test_annotation_without_lines_matches_exact_format(
    file_path: str, use_none_start: bool, use_none_end: bool
) -> None:
    """When start_line or end_line is None, output matches exactly '<!-- target: <path> -->'."""
    # Ensure at least one is None
    if not use_none_start and not use_none_end:
        start_line = None
        end_line = None
    else:
        start_line = None if use_none_start else 10
        end_line = None if use_none_end else 20

    result = CodeSearchResult(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        found=True,
    )

    annotation = _annotator._format_annotation(result)

    # Verify exact format via regex
    match = _ANNOTATION_WITHOUT_LINES.match(annotation)
    assert match is not None, (
        f"Annotation does not match expected format.\n"
        f"  Got:      '{annotation}'\n"
        f"  Expected: '<!-- target: {file_path} -->'"
    )

    # Verify extracted path matches input
    assert match.group(1) == file_path, (
        f"Path mismatch: expected '{file_path}', got '{match.group(1)}'"
    )

    # Verify it does NOT match the lines format
    lines_match = _ANNOTATION_WITH_LINES.match(annotation)
    assert lines_match is None, (
        f"Annotation should NOT have lines portion when start_line or end_line is None.\n"
        f"  Got: '{annotation}'"
    )
