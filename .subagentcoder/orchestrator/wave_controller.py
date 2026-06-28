"""Wave execution controller for orchestrator dispatch.

Controls how many tasks within a wave execute concurrently based on the wave's
concurrency setting and optional global execution config overrides.

Behavioral contract:
- concurrency: "parallel" — dispatch all tasks at once (current default).
- concurrency: "sequential" — dispatch one at a time, wait for completion.
- concurrency: N (integer 1–64) — semaphore-limited concurrent dispatch.
- "parallel": false legacy alias → treated as concurrency: "sequential".
- Global executionMode: "sequential" overrides all wave annotations.
- On task failure in sequential/limited mode: cancel remaining unstarted tasks,
  report failure.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from models.task_graph import ExecutionConfig, WaveConfig


@dataclass
class TaskResult:
    """Result of a single dispatched task."""

    task_id: str
    success: bool
    output: Any = None
    error: str | None = None


# Type alias for the dispatch function provided by the caller.
# It takes a task_id string and returns a TaskResult.
DispatchFn = Callable[[str], Awaitable[TaskResult]]


def resolve_effective_concurrency(
    wave: WaveConfig,
    global_config: ExecutionConfig | None = None,
) -> int:
    """Determine the effective concurrency limit for a wave.

    Resolution order:
    1. If global_config.execution_mode == "sequential", return 1 (override).
    2. Parse wave.concurrency:
       - "sequential" → 1
       - "parallel" → len(wave.tasks) (unbounded, all at once)
       - int N in [1, 64] → N

    The legacy alias {"parallel": false} should be normalized to
    concurrency="sequential" before reaching this function (see
    parse_legacy_parallel_field).

    Args:
        wave: The wave configuration with concurrency and task list.
        global_config: Optional global execution config that may override.

    Returns:
        Integer concurrency limit. A value >= len(wave.tasks) means fully
        parallel (no constraint).
    """
    # Global override takes precedence
    if global_config is not None and global_config.execution_mode == "sequential":
        return 1

    concurrency = wave.concurrency

    if concurrency == "sequential":
        return 1
    elif concurrency == "parallel":
        # No limit — return task count so semaphore is effectively unbounded
        return len(wave.tasks) if wave.tasks else 1
    elif isinstance(concurrency, int):
        # Already validated by WaveConfig.__post_init__ to be in [1, 64]
        return concurrency
    else:
        # Should not reach here due to WaveConfig validation, but be defensive
        raise ValueError(
            f"Unexpected concurrency value: {concurrency!r}"
        )


def parse_legacy_parallel_field(raw_wave: dict[str, Any]) -> WaveConfig:
    """Parse a raw wave dict, handling the legacy "parallel": false alias.

    The legacy format uses:
        {"parallel": false, "id": "...", "tasks": [...]}

    This is normalized to:
        WaveConfig(id="...", concurrency="sequential", tasks=[...])

    If the raw dict already has a "concurrency" field, it takes precedence
    over the legacy "parallel" field.

    Args:
        raw_wave: Dictionary representation of a wave from task graph JSON.

    Returns:
        A validated WaveConfig instance.
    """
    wave_id = raw_wave.get("id", "")
    tasks = raw_wave.get("tasks", [])

    # If explicit concurrency field exists, use it directly
    if "concurrency" in raw_wave:
        return WaveConfig(
            id=wave_id,
            concurrency=raw_wave["concurrency"],
            tasks=tasks,
        )

    # Handle legacy "parallel" field
    parallel_value = raw_wave.get("parallel")
    if parallel_value is False:
        return WaveConfig(id=wave_id, concurrency="sequential", tasks=tasks)

    # Default: parallel (no annotation means parallel dispatch)
    return WaveConfig(id=wave_id, concurrency="parallel", tasks=tasks)


class WaveController:
    """Controls task dispatch within a wave respecting concurrency limits.

    Usage:
        controller = WaveController(wave_config, global_config)
        results = await controller.execute(dispatch_fn)

    The controller:
    1. Resolves effective concurrency from wave + global config.
    2. Dispatches tasks using an asyncio.Semaphore to bound parallelism.
    3. On failure in sequential/limited mode, cancels remaining tasks.
    4. Returns results for all attempted tasks.
    """

    def __init__(
        self,
        wave: WaveConfig,
        global_config: ExecutionConfig | None = None,
    ) -> None:
        self._wave = wave
        self._global_config = global_config
        self._effective_concurrency = resolve_effective_concurrency(
            wave, global_config
        )
        self._results: list[TaskResult] = []
        self._cancelled: list[str] = []
        self._failed: bool = False

    @property
    def effective_concurrency(self) -> int:
        """The resolved concurrency limit for this wave."""
        return self._effective_concurrency

    @property
    def is_bounded(self) -> bool:
        """True if concurrency is limited (not fully parallel)."""
        return self._effective_concurrency < len(self._wave.tasks)

    @property
    def results(self) -> list[TaskResult]:
        """Results from the most recent execute() call."""
        return list(self._results)

    @property
    def cancelled_tasks(self) -> list[str]:
        """Task IDs that were cancelled due to a prior failure."""
        return list(self._cancelled)

    async def execute(self, dispatch_fn: DispatchFn) -> list[TaskResult]:
        """Execute all tasks in the wave respecting the concurrency limit.

        Args:
            dispatch_fn: Async callable that takes a task_id and returns
                a TaskResult. This is the actual dispatch mechanism provided
                by the orchestrator.

        Returns:
            List of TaskResult for all tasks that were attempted. Cancelled
            tasks are not included in results but are available via
            cancelled_tasks property.
        """
        self._results = []
        self._cancelled = []
        self._failed = False

        tasks = self._wave.tasks
        if not tasks:
            return []

        concurrency = self._effective_concurrency
        is_fully_parallel = concurrency >= len(tasks)

        if is_fully_parallel:
            # Dispatch all at once — no failure cancellation in pure parallel
            return await self._execute_parallel(tasks, dispatch_fn)
        else:
            # Bounded execution with failure cancellation
            return await self._execute_bounded(tasks, concurrency, dispatch_fn)

    async def _execute_parallel(
        self, tasks: list[str], dispatch_fn: DispatchFn
    ) -> list[TaskResult]:
        """Dispatch all tasks concurrently without bounds.

        In fully parallel mode, all tasks are started simultaneously.
        No failure cancellation occurs (matching current default behavior).
        """
        coros = [dispatch_fn(task_id) for task_id in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._results.append(
                    TaskResult(
                        task_id=tasks[i],
                        success=False,
                        error=str(result),
                    )
                )
            else:
                self._results.append(result)

        return list(self._results)

    async def _execute_bounded(
        self,
        tasks: list[str],
        concurrency: int,
        dispatch_fn: DispatchFn,
    ) -> list[TaskResult]:
        """Dispatch tasks with semaphore-bounded concurrency.

        On task failure: cancel all remaining unstarted tasks and report
        the failure. Tasks already in-flight will complete but their results
        are still collected.
        """
        semaphore = asyncio.Semaphore(concurrency)
        failure_event = asyncio.Event()
        # Track which tasks have actually started
        started: set[str] = set()

        async def _guarded_dispatch(task_id: str) -> TaskResult | None:
            """Acquire semaphore, check for cancellation, then dispatch."""
            # Check if we should cancel before even waiting for semaphore
            if failure_event.is_set() and task_id not in started:
                self._cancelled.append(task_id)
                return None

            async with semaphore:
                # Re-check after acquiring semaphore (another task may have
                # failed while we were waiting)
                if failure_event.is_set() and task_id not in started:
                    self._cancelled.append(task_id)
                    return None

                started.add(task_id)
                try:
                    result = await dispatch_fn(task_id)
                except Exception as exc:
                    result = TaskResult(
                        task_id=task_id, success=False, error=str(exc)
                    )

                if not result.success:
                    failure_event.set()

                return result

        # Create all coroutines — semaphore gates actual execution
        coros = [_guarded_dispatch(task_id) for task_id in tasks]
        raw_results = await asyncio.gather(*coros)

        # Collect non-None results (None means cancelled)
        for result in raw_results:
            if result is not None:
                self._results.append(result)

        self._failed = failure_event.is_set()
        return list(self._results)

    def failure_report(self) -> str | None:
        """Generate a failure report if any task failed.

        Returns:
            A formatted failure report string, or None if all tasks succeeded.
        """
        if not self._failed:
            return None

        failed_tasks = [r for r in self._results if not r.success]
        if not failed_tasks:
            return None

        first_failure = failed_tasks[0]
        lines = [
            f"[ERROR] wave-controller: Task '{first_failure.task_id}' failed.",
        ]
        if first_failure.error:
            lines.append(f"  Error: {first_failure.error}")
        if first_failure.output:
            lines.append(f"  Output: {first_failure.output}")
        if self._cancelled:
            lines.append(
                f"  Cancelled {len(self._cancelled)} remaining task(s): "
                f"{', '.join(self._cancelled)}"
            )

        return "\n".join(lines)
