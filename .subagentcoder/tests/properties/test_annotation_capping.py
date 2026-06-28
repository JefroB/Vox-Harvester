# Feature: local-coder-workflow-improvements, Property 2: Multi-File Annotation Capping
"""Property test: For any task with N target symbols (1 <= N <= 100),
the annotate_task method SHALL emit exactly min(N, 50) annotation lines.

**Validates: Requirements 1.4**
"""

from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.task_annotator import CodeSearchResult, TaskAnnotator

MAX_ANNOTATIONS = 50

# Strategy: generate lists of 1-100 file path strings
file_targets = st.lists(
    st.text(
        min_size=3,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd", "Pc")),
    ),
    min_size=1,
    max_size=100,
)


def _mock_query(symbol: str) -> CodeSearchResult:
    """Mock CodeSearch to return a found result for any symbol."""
    return CodeSearchResult(file_path=symbol, start_line=None, end_line=None, found=True)


@settings(max_examples=100)
@given(target_symbols=file_targets)
def test_annotation_count_equals_min_n_50(target_symbols: list[str]) -> None:
    """The number of annotations emitted is exactly min(N, 50)."""
    annotator = TaskAnnotator(project_root=Path("/tmp/dummy"))

    with patch.object(annotator, "_query_codesearch", side_effect=_mock_query):
        result = annotator.annotate_task("test task", target_symbols)

    n = len(target_symbols)
    assert len(result.annotations) == min(n, MAX_ANNOTATIONS)


@settings(max_examples=100)
@given(target_symbols=file_targets)
def test_annotation_count_never_exceeds_50(target_symbols: list[str]) -> None:
    """Regardless of input size, annotations never exceed 50."""
    annotator = TaskAnnotator(project_root=Path("/tmp/dummy"))

    with patch.object(annotator, "_query_codesearch", side_effect=_mock_query):
        result = annotator.annotate_task("test task", target_symbols)

    assert len(result.annotations) <= MAX_ANNOTATIONS
