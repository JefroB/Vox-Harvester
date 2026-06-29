"""Property-based tests for sequential processing invariant.

**Validates: Requirements 6.1**

Tests the PURE LOGIC of the sequential dispatch mechanism without a running server.

The server logic being tested:

```typescript
let currentIsolationJob: IsolationJob | null = null;

async function dispatchNextIsolationJob() {
  if (currentIsolationJob) return; // At most one job in "processing" at any time
  const nextJob = isolationJobs.find(j => j.status === "pending");
  if (!nextJob) return;
  currentIsolationJob = nextJob;
  await processIsolationJob(nextJob);
}
```

We model this as a Python class and verify that for ANY sequence of
submit/complete/fail events, at most one job is ever in "processing" status,
and jobs are dispatched in FIFO order.
"""

from hypothesis import given, settings, assume
from hypothesis.strategies import composite, integers, lists, sampled_from
from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(Enum):
    SUBMIT = "submit"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class IsolationJob:
    """Minimal model of server-side IsolationJob."""
    job_id: str
    sample_id: str
    status: JobStatus = JobStatus.PENDING


@dataclass
class IsolationQueue:
    """Model of the server's sequential dispatch logic.

    Invariants:
    - At most one job in PROCESSING at any time.
    - Jobs dispatched in FIFO order (first pending job gets processed next).
    """
    jobs: List[IsolationJob] = field(default_factory=list)
    current_job: Optional[IsolationJob] = None
    _next_id: int = 0
    dispatch_order: List[str] = field(default_factory=list)

    def submit_job(self, sample_id: str) -> IsolationJob:
        """Submit a new job to the queue (status: pending)."""
        job = IsolationJob(job_id=f"job_{self._next_id}", sample_id=sample_id)
        self._next_id += 1
        self.jobs.append(job)
        self._dispatch_next()
        return job

    def complete_current(self) -> bool:
        """Mark the current processing job as completed. Returns False if no job processing."""
        if self.current_job is None:
            return False
        self.current_job.status = JobStatus.COMPLETED
        self.current_job = None
        self._dispatch_next()
        return True

    def fail_current(self) -> bool:
        """Mark the current processing job as failed. Returns False if no job processing."""
        if self.current_job is None:
            return False
        self.current_job.status = JobStatus.FAILED
        self.current_job = None
        self._dispatch_next()
        return True

    def _dispatch_next(self) -> None:
        """Dispatch the next pending job. Mirrors server's dispatchNextIsolationJob()."""
        if self.current_job is not None:
            return  # At most one job in "processing" at any time

        next_job = next((j for j in self.jobs if j.status == JobStatus.PENDING), None)
        if next_job is None:
            return

        self.current_job = next_job
        next_job.status = JobStatus.PROCESSING
        self.dispatch_order.append(next_job.job_id)

    def processing_count(self) -> int:
        """Count jobs currently in PROCESSING status."""
        return sum(1 for j in self.jobs if j.status == JobStatus.PROCESSING)

    def pending_count(self) -> int:
        """Count jobs currently in PENDING status."""
        return sum(1 for j in self.jobs if j.status == JobStatus.PENDING)


@composite
def event_sequences(draw, min_events=2, max_events=50):
    """Generate a random sequence of queue events (submit, complete, fail).

    Ensures at least one submit event exists so there's something to process.
    """
    num_events = draw(integers(min_value=min_events, max_value=max_events))
    events = []
    # Always start with at least one submit
    events.append(EventType.SUBMIT)
    for _ in range(num_events - 1):
        event = draw(sampled_from([EventType.SUBMIT, EventType.COMPLETE, EventType.FAIL]))
        events.append(event)
    return events


@given(events=event_sequences(min_events=2, max_events=50))
@settings(max_examples=100)
def test_at_most_one_processing_at_any_time(events: List[EventType]) -> None:
    """For any sequence of submit/complete/fail events, at most one job
    SHALL be in 'processing' status at any given time.

    **Validates: Requirements 6.1**
    """
    queue = IsolationQueue()

    for event in events:
        if event == EventType.SUBMIT:
            queue.submit_job(sample_id=f"sample_{queue._next_id}")
        elif event == EventType.COMPLETE:
            queue.complete_current()
        elif event == EventType.FAIL:
            queue.fail_current()

        # INVARIANT: at most one job processing after every event
        assert queue.processing_count() <= 1, (
            f"Invariant violated: {queue.processing_count()} jobs in processing state "
            f"after event {event.value}. Jobs: {[(j.job_id, j.status.value) for j in queue.jobs]}"
        )


@given(events=event_sequences(min_events=3, max_events=40))
@settings(max_examples=100)
def test_fifo_dispatch_order(events: List[EventType]) -> None:
    """For any sequence of events, jobs SHALL transition from 'pending' to
    'processing' in the order they were submitted (FIFO).

    **Validates: Requirements 6.1**
    """
    queue = IsolationQueue()
    submission_order: List[str] = []

    for event in events:
        if event == EventType.SUBMIT:
            job = queue.submit_job(sample_id=f"sample_{queue._next_id - 1}")
            submission_order.append(job.job_id)
        elif event == EventType.COMPLETE:
            queue.complete_current()
        elif event == EventType.FAIL:
            queue.fail_current()

    # dispatch_order should be a prefix of submission_order
    # (only submitted jobs that got dispatched, in submission order)
    for i, dispatched_id in enumerate(queue.dispatch_order):
        assert dispatched_id == submission_order[i], (
            f"FIFO violated at position {i}: dispatched {dispatched_id} "
            f"but expected {submission_order[i]}. "
            f"Dispatch order: {queue.dispatch_order}, "
            f"Submission order: {submission_order}"
        )


@given(events=event_sequences(min_events=5, max_events=30))
@settings(max_examples=100)
def test_pending_jobs_remain_pending_while_processing(events: List[EventType]) -> None:
    """While a job is in 'processing', all other pending jobs SHALL remain
    in 'pending' status (none skip to processing).

    **Validates: Requirements 6.1**
    """
    queue = IsolationQueue()

    for event in events:
        if event == EventType.SUBMIT:
            queue.submit_job(sample_id=f"sample_{queue._next_id}")
        elif event == EventType.COMPLETE:
            queue.complete_current()
        elif event == EventType.FAIL:
            queue.fail_current()

        # If there's a current job processing, all other non-terminal jobs must be pending
        if queue.current_job is not None:
            for job in queue.jobs:
                if job is queue.current_job:
                    assert job.status == JobStatus.PROCESSING
                elif job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
                    assert job.status == JobStatus.PENDING, (
                        f"Job {job.job_id} has status {job.status.value} while "
                        f"{queue.current_job.job_id} is processing. "
                        f"Expected 'pending'."
                    )


@given(num_submits=integers(min_value=1, max_value=25))
@settings(max_examples=100)
def test_rapid_completion_maintains_invariant(num_submits: int) -> None:
    """When jobs complete or fail rapidly (immediately after dispatch),
    the invariant still holds: at most one processing at a time.

    **Validates: Requirements 6.1**
    """
    queue = IsolationQueue()

    # Submit all jobs first
    for i in range(num_submits):
        queue.submit_job(sample_id=f"sample_{i}")
        assert queue.processing_count() <= 1

    # Now rapidly complete/fail them all
    for i in range(num_submits):
        assert queue.processing_count() <= 1
        if i % 3 == 0:
            queue.fail_current()
        else:
            queue.complete_current()
        assert queue.processing_count() <= 1

    # All jobs should be terminal
    for job in queue.jobs:
        assert job.status in (JobStatus.COMPLETED, JobStatus.FAILED), (
            f"Job {job.job_id} still in {job.status.value} after all completions"
        )
