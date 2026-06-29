"""Property-based tests for queue overflow rejection.

**Validates: Requirements 6.2**

Tests the PURE LOGIC of the queue-full decision without a running server.

The server logic being tested:
typescript
const MAX_ISOLATION_QUEUE_DEPTH = 20;
function getPendingIsolationJobCount(): number {
  return isolationJobs.filter(job => job.status === 'pending').length;
}
// In the endpoint handler:
const pendingCount = getPendingIsolationJobCount();
if (pendingCount >= MAX_ISOLATION_QUEUE_DEPTH) {
  return res.status(503).json({ error: 'Isolation queue is full', queueDepth: pendingCount });
}
"""

from hypothesis import given, settings
import hypothesis.strategies as st


MAX_QUEUE_DEPTH = 20


def should_reject_request(pending_count: int) -> tuple[bool, dict | None]:
    """Return True and error response if pending_count >= MAX_QUEUE_DEPTH, else False and None."""
    if pending_count >= MAX_QUEUE_DEPTH:
        return True, {'error': 'Isolation queue is full', 'queueDepth': pending_count}
    return False, None


@given(pending_count=st.integers(min_value=20, max_value=100))
@settings(max_examples=100)
def test_queue_at_or_above_max_rejects(pending_count: int) -> None:
    """For any pending_count from 20 to 100, should_reject is True and response contains error message and queueDepth == pending_count.

    **Validates: Requirements 6.2**
    """
    should_reject, response = should_reject_request(pending_count)
    assert should_reject
    assert response is not None
    assert 'error' in response
    assert response['queueDepth'] == pending_count


@given(pending_count=st.integers(min_value=0, max_value=19))
@settings(max_examples=100)
def test_queue_below_max_allows(pending_count: int) -> None:
    """For any pending_count from 0 to 19, should_reject is False and response is None.

    **Validates: Requirements 6.2**
    """
    should_reject, response = should_reject_request(pending_count)
    assert not should_reject
    assert response is None


def test_boundary_exactly_at_max() -> None:
    """Boundary verification: depth 19 allows, depth 20 rejects, depth 21 rejects.

    **Validates: Requirements 6.2**
    """
    should_reject_19, response_19 = should_reject_request(19)
    assert not should_reject_19
    assert response_19 is None

    should_reject_20, response_20 = should_reject_request(20)
    assert should_reject_20
    assert response_20 is not None
    assert 'error' in response_20
    assert response_20['queueDepth'] == 20

    should_reject_21, response_21 = should_reject_request(21)
    assert should_reject_21
    assert response_21 is not None
    assert 'error' in response_21
    assert response_21['queueDepth'] == 21


@given(pending_count=st.integers(min_value=20))
@settings(max_examples=100)
def test_rejection_error_contains_queue_depth(pending_count: int) -> None:
    """For any pending_count >= 20, the error dict must have 'error' key with 'queue is full' text and 'queueDepth' key equal to pending_count.

    **Validates: Requirements 6.2**
    """
    should_reject, response = should_reject_request(pending_count)
    assert should_reject
    assert response is not None
    assert 'error' in response
    assert response['error'] == 'Isolation queue is full'
    assert response['queueDepth'] == pending_count