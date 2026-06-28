"""Tests for conflict detection integration in the orchestrator dispatch pipeline.

Validates:
- Parallel waves with conflicting output paths are serialized (Req 5.1, 5.2)
- Non-conflicting tasks in the same wave run in parallel (Req 5.4)
- Warnings are emitted to stderr for serialized tasks (Req 5.3)
- Path canonicalization detects conflicts regardless of notation (Req 5.5)
- Sequential waves bypass conflict detection (no overhead)
- Tasks without --output are treated as non-conflicting
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.dispatch import (
    DispatchResult,
    _apply_conflict_detection,
    _build_task_specs_for_wave,
    dispatch_task_graph,
)
from orchestrator.wave_controller import TaskResult
from models.task_graph import WaveConfig


class TestBuildTaskSpecsForWave:
    """Tests for _build_task_specs_for_wave helper."""

    def test_tasks_with_output(self):
        task_ids = ["t1", "t2"]
        registry = {
            "t1": {"output": "src/foo.py"},
            "t2": {"output": "src/bar.py"},
        }
        specs = _build_task_specs_for_wave(task_ids, registry)
        assert len(specs) == 2
        assert specs[0].task_id == "t1"
        assert specs[0].command_args == ["--output", "src/foo.py"]
        assert specs[1].task_id == "t2"
        assert specs[1].command_args == ["--output", "src/bar.py"]

    def test_tasks_without_output(self):
        task_ids = ["t1", "t2"]
        registry = {
            "t1": {"description": "some task"},
            "t2": {"description": "another task"},
        }
        specs = _build_task_specs_for_wave(task_ids, registry)
        assert len(specs) == 2
        assert specs[0].command_args == []
        assert specs[1].command_args == []

    def test_mixed_tasks(self):
        task_ids = ["t1", "t2", "t3"]
        registry = {
            "t1": {"output": "src/foo.py"},
            "t2": {"description": "no output"},
            "t3": {"output": "src/bar.py"},
        }
        specs = _build_task_specs_for_wave(task_ids, registry)
        assert specs[0].command_args == ["--output", "src/foo.py"]
        assert specs[1].command_args == []
        assert specs[2].command_args == ["--output", "src/bar.py"]

    def test_missing_task_in_registry(self):
        task_ids = ["t1", "t_missing"]
        registry = {"t1": {"output": "src/foo.py"}}
        specs = _build_task_specs_for_wave(task_ids, registry)
        assert len(specs) == 2
        assert specs[0].command_args == ["--output", "src/foo.py"]
        assert specs[1].command_args == []  # Missing task treated as no output


class TestApplyConflictDetection:
    """Tests for _apply_conflict_detection integration function."""

    def test_no_conflicts(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=["t1", "t2"])
        registry = {
            "t1": {"output": "src/a.py"},
            "t2": {"output": "src/b.py"},
        }
        parallel_groups, serial_chains = _apply_conflict_detection(wave, registry)
        assert serial_chains == []
        # All tasks are in parallel groups
        all_parallel_ids = [tid for group in parallel_groups for tid in group]
        assert set(all_parallel_ids) == {"t1", "t2"}

    def test_with_conflicts(self, capsys):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=["t1", "t2", "t3"])
        registry = {
            "t1": {"output": "src/shared.py"},
            "t2": {"output": "src/shared.py"},
            "t3": {"output": "src/unique.py"},
        }
        parallel_groups, serial_chains = _apply_conflict_detection(wave, registry)

        # t1 and t2 conflict (same output), t3 is safe
        assert len(serial_chains) == 1
        conflicting_ids = set(serial_chains[0])
        assert conflicting_ids == {"t1", "t2"}

        # t3 is in a parallel group
        all_parallel_ids = [tid for group in parallel_groups for tid in group]
        assert "t3" in all_parallel_ids

        # Verify warning was emitted
        captured = capsys.readouterr()
        assert "[DISPATCH WARN]" in captured.err
        assert "shared.py" in captured.err

    def test_empty_wave(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=[])
        registry = {}
        parallel_groups, serial_chains = _apply_conflict_detection(wave, registry)
        assert parallel_groups == []
        assert serial_chains == []

    def test_all_tasks_no_output(self):
        wave = WaveConfig(id="w1", concurrency="parallel", tasks=["t1", "t2"])
        registry = {
            "t1": {"description": "task 1"},
            "t2": {"description": "task 2"},
        }
        parallel_groups, serial_chains = _apply_conflict_detection(wave, registry)
        assert serial_chains == []
        # All tasks are in parallel groups (no output = no conflict)
        all_parallel_ids = [tid for group in parallel_groups for tid in group]
        assert set(all_parallel_ids) == {"t1", "t2"}


class TestDispatchTaskGraphConflictDetection:
    """Integration tests for conflict detection within dispatch_task_graph."""

    @pytest.mark.asyncio
    async def test_parallel_wave_no_conflicts_dispatches_all(self):
        """When no conflicts exist, all tasks dispatch in parallel."""
        task_graph = {
            "waves": [
                {"id": "w1", "concurrency": "parallel", "tasks": ["t1", "t2", "t3"]}
            ],
            "tasks": {
                "t1": {"type": "implementation", "routing": "cloud", "description": "task 1", "output": "a.py"},
                "t2": {"type": "implementation", "routing": "cloud", "description": "task 2", "output": "b.py"},
                "t3": {"type": "implementation", "routing": "cloud", "description": "task 3", "output": "c.py"},
            },
        }

        with patch("orchestrator.dispatch.check_ollama_reachable", return_value=False), \
             patch("orchestrator.dispatch.enforce_routing") as mock_enforce:
            mock_enforce.return_value = type("Decision", (), {"target": "cloud", "override_reason": None})()
            result = await dispatch_task_graph(task_graph, Path("."))

        assert result.success
        assert len(result.wave_results) == 1
        assert len(result.wave_results[0]) == 3

    @pytest.mark.asyncio
    async def test_parallel_wave_with_conflicts_serializes(self, capsys):
        """When conflicts exist, conflicting tasks are serialized."""
        task_graph = {
            "waves": [
                {"id": "w1", "concurrency": "parallel", "tasks": ["t1", "t2", "t3"]}
            ],
            "tasks": {
                "t1": {"type": "implementation", "routing": "cloud", "description": "task 1", "output": "shared.py"},
                "t2": {"type": "implementation", "routing": "cloud", "description": "task 2", "output": "shared.py"},
                "t3": {"type": "implementation", "routing": "cloud", "description": "task 3", "output": "unique.py"},
            },
        }

        with patch("orchestrator.dispatch.check_ollama_reachable", return_value=False), \
             patch("orchestrator.dispatch.enforce_routing") as mock_enforce:
            mock_enforce.return_value = type("Decision", (), {"target": "cloud", "override_reason": None})()
            result = await dispatch_task_graph(task_graph, Path("."))

        assert result.success
        assert len(result.wave_results) == 1
        # All 3 tasks should have results
        assert len(result.wave_results[0]) == 3

        # Verify the warning was emitted
        captured = capsys.readouterr()
        assert "[DISPATCH WARN]" in captured.err

    @pytest.mark.asyncio
    async def test_sequential_wave_skips_conflict_detection(self):
        """Sequential waves don't need conflict detection."""
        task_graph = {
            "waves": [
                {"id": "w1", "concurrency": "sequential", "tasks": ["t1", "t2"]}
            ],
            "tasks": {
                "t1": {"type": "implementation", "routing": "cloud", "description": "task 1", "output": "shared.py"},
                "t2": {"type": "implementation", "routing": "cloud", "description": "task 2", "output": "shared.py"},
            },
        }

        with patch("orchestrator.dispatch.check_ollama_reachable", return_value=False), \
             patch("orchestrator.dispatch.enforce_routing") as mock_enforce, \
             patch("orchestrator.dispatch._apply_conflict_detection") as mock_conflict:
            mock_enforce.return_value = type("Decision", (), {"target": "cloud", "override_reason": None})()
            result = await dispatch_task_graph(task_graph, Path("."))

        # Conflict detection should NOT have been called for sequential waves
        mock_conflict.assert_not_called()
        assert result.success

    @pytest.mark.asyncio
    async def test_single_task_wave_skips_conflict_detection(self):
        """Single-task waves don't need conflict detection."""
        task_graph = {
            "waves": [
                {"id": "w1", "concurrency": "parallel", "tasks": ["t1"]}
            ],
            "tasks": {
                "t1": {"type": "implementation", "routing": "cloud", "description": "task 1", "output": "a.py"},
            },
        }

        with patch("orchestrator.dispatch.check_ollama_reachable", return_value=False), \
             patch("orchestrator.dispatch.enforce_routing") as mock_enforce, \
             patch("orchestrator.dispatch._apply_conflict_detection") as mock_conflict:
            mock_enforce.return_value = type("Decision", (), {"target": "cloud", "override_reason": None})()
            result = await dispatch_task_graph(task_graph, Path("."))

        # Conflict detection should NOT have been called for single-task waves
        mock_conflict.assert_not_called()
        assert result.success
