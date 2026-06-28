"""Smoke tests for the wave execution controller.

Validates the core behavioral contract:
- "parallel" dispatches all tasks at once.
- "sequential" dispatches one at a time.
- Integer N limits to N concurrent tasks.
- Legacy "parallel": false → sequential.
- Global executionMode: "sequential" override.
- Failure cancellation in bounded modes.
"""

from __future__ import annotations

import asyncio

import pytest

from models.task_graph import ExecutionConfig, WaveConfig
from orchestrator.wave_controller import (
    TaskResult,
    WaveController,
    parse_legacy_parallel_field,
    resolve_effective_concurrency,
)


# ---------------------------------------------------------------------------
# resolve_effective_concurrency tests
# ---------------------------------------------------------------------------


class TestResolveEffectiveConcurrency:
    """Tests for resolve_effective_concurrency."""

    def test_parallel_returns_task_count(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=["a", "b", "c"])
        assert resolve_effective_concurrency(wave) == 3

    def test_sequential_returns_one(self):
        wave = WaveConfig(id="w1", concurrency="sequential", tasks=["a", "b", "c"])
        assert resolve_effective_concurrency(wave) == 1

    def test_integer_concurrency_passthrough(self):
        wave = WaveConfig(id="w1", concurrency=3, tasks=["a", "b", "c", "d"])
        assert resolve_effective_concurrency(wave) == 3

    def test_global_sequential_overrides_parallel(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=["a", "b", "c"])
        config = ExecutionConfig(execution_mode="sequential")
        assert resolve_effective_concurrency(wave, config) == 1

    def test_global_sequential_overrides_integer(self):
        wave = WaveConfig(id="w1", concurrency=4, tasks=["a", "b", "c", "d"])
        config = ExecutionConfig(execution_mode="sequential")
        assert resolve_effective_concurrency(wave, config) == 1

    def test_global_parallel_does_not_override(self):
        wave = WaveConfig(id="w1", concurrency="sequential", tasks=["a", "b"])
        config = ExecutionConfig(execution_mode="parallel")
        assert resolve_effective_concurrency(wave, config) == 1

    def test_empty_task_list_parallel(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=[])
        assert resolve_effective_concurrency(wave) == 1


# ---------------------------------------------------------------------------
# parse_legacy_parallel_field tests
# ---------------------------------------------------------------------------


class TestParseLegacyParallelField:
    """Tests for the legacy "parallel": false alias."""

    def test_parallel_false_becomes_sequential(self):
        raw = {"id": "wave-1", "parallel": False, "tasks": ["t1", "t2"]}
        wave = parse_legacy_parallel_field(raw)
        assert wave.concurrency == "sequential"
        assert wave.tasks == ["t1", "t2"]

    def test_explicit_concurrency_takes_precedence(self):
        raw = {
            "id": "wave-1",
            "concurrency": 3,
            "parallel": False,
            "tasks": ["t1", "t2", "t3"],
        }
        wave = parse_legacy_parallel_field(raw)
        assert wave.concurrency == 3

    def test_no_annotation_defaults_to_parallel(self):
        raw = {"id": "wave-1", "tasks": ["t1", "t2"]}
        wave = parse_legacy_parallel_field(raw)
        assert wave.concurrency == "parallel"

    def test_parallel_true_treated_as_default(self):
        raw = {"id": "wave-1", "parallel": True, "tasks": ["t1"]}
        wave = parse_legacy_parallel_field(raw)
        # parallel: True is not the legacy alias, default to parallel
        assert wave.concurrency == "parallel"


# ---------------------------------------------------------------------------
# WaveController async execution tests
# ---------------------------------------------------------------------------


class TestWaveControllerParallel:
    """Tests for fully parallel dispatch."""

    @pytest.mark.asyncio
    async def test_all_tasks_dispatched_at_once(self):
        """In parallel mode, all tasks start concurrently."""
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=["a", "b", "c"])
        controller = WaveController(wave)

        dispatch_order: list[str] = []

        async def dispatch(task_id: str) -> TaskResult:
            dispatch_order.append(task_id)
            await asyncio.sleep(0.01)
            return TaskResult(task_id=task_id, success=True)

        results = await controller.execute(dispatch)
        assert len(results) == 3
        assert all(r.success for r in results)
        assert set(dispatch_order) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_parallel_no_cancellation_on_failure(self):
        """Parallel mode does not cancel tasks on failure."""
        wave = WaveConfig(
            id="w1", concurrency="parallel", tasks=["a", "b", "c"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "b":
                return TaskResult(task_id=task_id, success=False, error="fail")
            await asyncio.sleep(0.01)
            return TaskResult(task_id=task_id, success=True)

        results = await controller.execute(dispatch)
        assert len(results) == 3
        assert controller.cancelled_tasks == []


class TestWaveControllerSequential:
    """Tests for sequential dispatch."""

    @pytest.mark.asyncio
    async def test_sequential_one_at_a_time(self):
        """Sequential mode dispatches one task at a time in order."""
        wave = WaveConfig(
            id="w1", concurrency="sequential", tasks=["a", "b", "c"]
        )
        controller = WaveController(wave)

        max_concurrent = 0
        current_concurrent = 0
        order: list[str] = []

        async def dispatch(task_id: str) -> TaskResult:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            order.append(task_id)
            await asyncio.sleep(0.01)
            current_concurrent -= 1
            return TaskResult(task_id=task_id, success=True)

        results = await controller.execute(dispatch)
        assert len(results) == 3
        assert max_concurrent == 1
        assert order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_sequential_cancels_on_failure(self):
        """Sequential mode cancels remaining tasks after failure."""
        wave = WaveConfig(
            id="w1", concurrency="sequential", tasks=["a", "b", "c", "d"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "b":
                return TaskResult(task_id=task_id, success=False, error="boom")
            await asyncio.sleep(0.01)
            return TaskResult(task_id=task_id, success=True)

        results = await controller.execute(dispatch)
        # a succeeds, b fails, c and d should be cancelled
        executed_ids = {r.task_id for r in results}
        assert "a" in executed_ids
        assert "b" in executed_ids
        assert "c" not in executed_ids
        assert "d" not in executed_ids
        cancelled = set(controller.cancelled_tasks)
        assert "c" in cancelled
        assert "d" in cancelled


class TestWaveControllerBounded:
    """Tests for integer-bounded concurrency."""

    @pytest.mark.asyncio
    async def test_bounded_respects_limit(self):
        """Bounded mode never exceeds N concurrent tasks."""
        wave = WaveConfig(
            id="w1", concurrency=2, tasks=["a", "b", "c", "d", "e"]
        )
        controller = WaveController(wave)

        max_concurrent = 0
        current_concurrent = 0

        async def dispatch(task_id: str) -> TaskResult:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.02)
            current_concurrent -= 1
            return TaskResult(task_id=task_id, success=True)

        results = await controller.execute(dispatch)
        assert len(results) == 5
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_bounded_cancels_on_failure(self):
        """Bounded mode cancels remaining unstarted tasks after failure."""
        wave = WaveConfig(
            id="w1", concurrency=1, tasks=["a", "b", "c"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "a":
                return TaskResult(task_id=task_id, success=False, error="err")
            return TaskResult(task_id=task_id, success=True)

        results = await controller.execute(dispatch)
        # Only "a" should have executed
        executed_ids = {r.task_id for r in results}
        assert "a" in executed_ids
        assert "b" not in executed_ids
        assert "c" not in executed_ids
        # b and c should be cancelled
        cancelled = set(controller.cancelled_tasks)
        assert "b" in cancelled
        assert "c" in cancelled


class TestWaveControllerGlobalOverride:
    """Tests for global executionMode override."""

    @pytest.mark.asyncio
    async def test_global_sequential_forces_sequential(self):
        """Global sequential override forces one-at-a-time execution."""
        wave = WaveConfig(
            id="w1", concurrency="parallel", tasks=["a", "b", "c"]
        )
        config = ExecutionConfig(execution_mode="sequential")
        controller = WaveController(wave, config)

        assert controller.effective_concurrency == 1

        max_concurrent = 0
        current_concurrent = 0

        async def dispatch(task_id: str) -> TaskResult:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)
            current_concurrent -= 1
            return TaskResult(task_id=task_id, success=True)

        await controller.execute(dispatch)
        assert max_concurrent == 1


class TestWaveControllerFailureReport:
    """Tests for failure_report method."""

    @pytest.mark.asyncio
    async def test_failure_report_on_failed_task(self):
        wave = WaveConfig(
            id="w1", concurrency="sequential", tasks=["a", "b", "c"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "a":
                return TaskResult(
                    task_id="a", success=False, error="test failure"
                )
            return TaskResult(task_id=task_id, success=True)

        await controller.execute(dispatch)
        report = controller.failure_report()
        assert report is not None
        assert "task 'a' failed" in report.lower() or "Task 'a' failed" in report

    @pytest.mark.asyncio
    async def test_failure_report_includes_error_message(self):
        """failure_report includes the task ID and error output."""
        wave = WaveConfig(
            id="w1", concurrency="sequential", tasks=["x", "y", "z"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "x":
                return TaskResult(
                    task_id="x", success=False, error="connection refused"
                )
            return TaskResult(task_id=task_id, success=True)

        await controller.execute(dispatch)
        report = controller.failure_report()
        assert report is not None
        # Report must contain the failing task identifier
        assert "x" in report
        # Report must contain the error message
        assert "connection refused" in report

    @pytest.mark.asyncio
    async def test_failure_report_lists_cancelled_tasks(self):
        """failure_report includes the list of cancelled tasks."""
        wave = WaveConfig(
            id="w1", concurrency="sequential", tasks=["a", "b", "c", "d"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "a":
                return TaskResult(
                    task_id="a", success=False, error="kaboom"
                )
            return TaskResult(task_id=task_id, success=True)

        await controller.execute(dispatch)
        report = controller.failure_report()
        assert report is not None
        # Cancelled tasks should be mentioned in the report
        assert "b" in report
        assert "c" in report
        assert "d" in report

    @pytest.mark.asyncio
    async def test_no_failure_report_on_success(self):
        wave = WaveConfig(
            id="w1", concurrency="sequential", tasks=["a", "b"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            return TaskResult(task_id=task_id, success=True)

        await controller.execute(dispatch)
        assert controller.failure_report() is None

    @pytest.mark.asyncio
    async def test_failure_report_with_output(self):
        """failure_report includes task output when available."""
        wave = WaveConfig(
            id="w1", concurrency=2, tasks=["t1", "t2", "t3"]
        )
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            if task_id == "t1":
                return TaskResult(
                    task_id="t1",
                    success=False,
                    error="assertion error",
                    output="Expected 5 got 3",
                )
            await asyncio.sleep(0.05)
            return TaskResult(task_id=task_id, success=True)

        await controller.execute(dispatch)
        report = controller.failure_report()
        assert report is not None
        assert "t1" in report
        assert "assertion error" in report
        assert "Expected 5 got 3" in report


class TestWaveControllerEmptyWave:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_wave(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=[])
        controller = WaveController(wave)

        async def dispatch(task_id: str) -> TaskResult:
            raise AssertionError("Should not be called")

        results = await controller.execute(dispatch)
        assert results == []
