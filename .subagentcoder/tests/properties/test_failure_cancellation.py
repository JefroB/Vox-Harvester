# Feature: subagent-improvements, Property 2: Failure Cancellation in Bounded Waves
"""Property-based tests for failure cancellation in bounded waves.

**Validates: Requirements 1.6**

For any wave executing under sequential or concurrency-limited mode, if task at
index K fails, then all tasks at indices K+1 through N-1 shall never be started,
and the failure report shall contain the failing task's identifier.
"""

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from models.task_graph import WaveConfig
from orchestrator.wave_controller import WaveController, TaskResult


# --- Strategies ---

# Wave sizes from 3 to 15 tasks
wave_sizes = st.integers(min_value=3, max_value=15)

# Sequential or bounded concurrency (1-3) — never fully parallel
bounded_concurrency = st.one_of(
    st.just("sequential"),
    st.integers(min_value=1, max_value=3),
)


@st.composite
def failure_scenarios(draw):
    """Generate a wave size, a failure index K, and a bounded concurrency setting.

    We ensure the wave is truly bounded (effective concurrency < task count)
    so failure cancellation logic is exercised. This means:
    - sequential (effective_c=1): wave size must be >= 2
    - integer N: wave size must be > N
    """
    concurrency = draw(bounded_concurrency)
    # Resolve effective concurrency as the controller would
    effective_c = 1 if concurrency == "sequential" else concurrency
    # Wave size must exceed effective concurrency to be truly bounded
    min_size = effective_c + 1
    size = draw(st.integers(min_value=max(min_size, 3), max_value=15))
    # K must be within [0, size-2] to ensure at least one task after K
    k = draw(st.integers(min_value=0, max_value=size - 2))
    return size, k, concurrency, effective_c


# --- Property Tests ---


@pytest.mark.asyncio
@settings(max_examples=100)
@given(scenario=failure_scenarios())
async def test_failure_cancellation_in_bounded_waves(scenario):
    """Tasks that were never started shall appear in cancelled_tasks,
    no cancelled task was ever dispatched, and the failure report shall
    contain the failing task's identifier.

    With bounded concurrency C, when task K fails:
    - Tasks already in-flight (acquired semaphore) may complete normally.
    - Tasks that haven't acquired the semaphore are cancelled.
    - All cancelled tasks must never have been started.
    - The failure report must name the failing task.
    """
    size, k, concurrency, effective_c = scenario

    tasks = [f"task-{i}" for i in range(size)]
    wave = WaveConfig(id="test-wave", concurrency=concurrency, tasks=tasks)
    controller = WaveController(wave)

    # Track which tasks were actually started (dispatch function was called)
    started_tasks = []

    async def dispatch_fn(task_id: str) -> TaskResult:
        started_tasks.append(task_id)
        # Simulate work
        await asyncio.sleep(0)

        # Fail at the K-th task
        if task_id == f"task-{k}":
            return TaskResult(task_id=task_id, success=False, error="simulated failure")

        return TaskResult(task_id=task_id, success=True)

    await controller.execute(dispatch_fn)

    cancelled = set(controller.cancelled_tasks)
    started_set = set(started_tasks)

    # Property 1: No cancelled task was ever started (dispatch function never called)
    for task_id in cancelled:
        assert task_id not in started_set, (
            f"Task '{task_id}' is in cancelled_tasks but was also started "
            f"(concurrency={concurrency!r}, wave_size={size}, failure_index={k})"
        )

    # Property 2: Every task after K is either started (was in-flight) or cancelled
    # — no task after K is silently lost
    for i in range(k + 1, size):
        task_id = f"task-{i}"
        assert task_id in started_set or task_id in cancelled, (
            f"Task '{task_id}' at index {i} is neither started nor cancelled "
            f"(concurrency={concurrency!r}, wave_size={size}, failure_index={k})"
        )

    # Property 3: At least one task after K must be cancelled (since we ensured
    # there are tasks after K and concurrency is bounded)
    tasks_after_k = {f"task-{i}" for i in range(k + 1, size)}
    cancelled_after_k = tasks_after_k & cancelled
    # With bounded concurrency, if there are more tasks after K than slots
    # remaining, some must be cancelled. With concurrency 1 (sequential),
    # ALL tasks after K must be cancelled.
    if effective_c == 1:
        # Sequential: every task after K is cancelled
        assert cancelled_after_k == tasks_after_k, (
            f"In sequential mode, all tasks after K={k} should be cancelled. "
            f"Expected cancelled: {tasks_after_k}, got: {cancelled_after_k}"
        )
    else:
        # Bounded: tasks beyond what could fit in concurrent slots with K
        # must be cancelled. At minimum, tasks that couldn't have acquired
        # the semaphore before the failure propagated should be cancelled.
        # We verify that at least one task after K is cancelled when there
        # are more remaining tasks than the concurrency limit.
        if len(tasks_after_k) > effective_c:
            assert len(cancelled_after_k) > 0, (
                f"With {len(tasks_after_k)} tasks after failure at K={k} and "
                f"concurrency={effective_c}, at least some should be cancelled"
            )

    # Property 4: The failure report contains the failing task's identifier
    report = controller.failure_report()
    assert report is not None, (
        f"failure_report() returned None after task-{k} failed "
        f"(concurrency={concurrency!r}, wave_size={size})"
    )
    assert f"task-{k}" in report, (
        f"failure_report() does not contain the failing task ID 'task-{k}': "
        f"{report!r}"
    )
