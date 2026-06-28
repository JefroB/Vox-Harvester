# Feature: local-coder-workflow-improvements, Property 10: Stderr Truncation
"""Property test: For ANY stderr string of length L passed to parse_exit_result
with a non-zero exit code:
- If L > 200: the truncated version (first 200 chars) appears in issues_found
- If L <= 200 and L > 0: the full string appears in issues_found
- If L == 0: no stderr entry in issues_found (just exit_code)

**Validates: Requirements 4.7**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from local_coder.stats_parser import parse_exit_result


@given(stderr=st.text(min_size=0, max_size=2000))
@settings(max_examples=100)
def test_stderr_truncation(stderr: str) -> None:
    """Stderr is truncated to 200 characters when length exceeds 200."""
    result, issues = parse_exit_result(exit_code=1, stderr=stderr)

    assert result == "fail"
    assert issues[0] == "exit_code:1"

    if len(stderr) > 200:
        assert stderr[:200] in issues
        # The full string should NOT be in issues (it was truncated)
        assert stderr not in issues
    elif len(stderr) > 0:
        assert stderr in issues
    else:
        # Empty stderr: only exit_code entry
        assert issues == ["exit_code:1"]
