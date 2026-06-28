# Feature: subagent-improvements, Property 1: Concurrency Invariant
"""Property-based tests for wave execution concurrency invariant.

**Validates: Requirements 1.1, 1.2, 1.3**

For any wave with concurrency setting C (where C is "sequential" treated as 1,
an integer N in 1–64, or "parallel" treated as task count), at no point during
execution shall the number of simultaneously in-flight tasks exceed C, and tasks
shall be dispatched in declaration order as slots become available.
"""

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from models.task_graph import WaveConfig
from orchestrator.wave_controller import WaveController, TaskResult


# --- Strategies ---

task_counts = st.integers(min_value=1, max_value=20)

concurrency_settings = st.one_of(
    st.just("sequential"),
    st.integers(min_value=1, max_value=10),
    st.just("parallel"),
)


# --- Property Tests ---


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    num_tasks=task_counts,
    concurrency=concurrency_settings,
)
async def test_concurrency_invariant(num_tasks, concurrency):
    """At no point shall the number of in-flight tasks exceed effective concurrency C."""
    tasks = [f"task-{i}" for i in range(num_tasks)]
    wave = WaveConfig(id="test-wave", concurrency=concurrency, tasks=tasks)
    controller = WaveController(wave)

    effective_c = controller.effective_concurrency

    # Shared mutable state to track concurrent dispatch
    current_concurrent = 0
    max_concurrent = 0
    dispatch_order = []
    lock = asyncio.Lock()

    async def dispatch_fn(task_id: str) -> TaskResult:
        nonlocal current_concurrent, max_concurrent

        async with lock:
            current_concurrent += 1
            dispatch_order.append(task_id)
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent

        # Yield control to allow other tasks to run concurrently
        await asyncio.sleep(0)

        async with lock:
            current_concurrent -= 1

        return TaskResult(task_id=task_id, success=True)

    await controller.execute(dispatch_fn)

    # Property: max concurrent tasks never exceeds effective concurrency
    assert max_concurrent <= effective_c, (
        f"Concurrency violated: max_concurrent={max_concurrent} > "
        f"effective_concurrency={effective_c} (setting={concurrency!r}, "
        f"num_tasks={num_tasks})"
    )

    # Property: tasks are dispatched in declaration order
    assert dispatch_order == tasks, (
        f"Declaration order violated: dispatched={dispatch_order}, "
        f"expected={tasks}"
    )
