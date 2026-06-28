"""Parallel write conflict detection for the orchestrator.

Detects when multiple Local_Coder tasks target the same output file and
partitions them into parallel-safe groups and serial chains.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TaskSpec:
    """Minimal representation of a dispatched local-coder task."""

    task_id: str
    command_args: list[str]


@dataclass
class ConflictResult:
    """Result of conflict detection."""

    parallel_groups: list[list[TaskSpec]]
    serial_chains: list[list[TaskSpec]]
    warnings: list[str]


def _extract_output_path(command_args: list[str]) -> str | None:
    """Extract the --output value from command args.

    Returns None if --output is not present or has no following value.
    """
    for i, arg in enumerate(command_args):
        if arg == "--output" and i + 1 < len(command_args):
            return command_args[i + 1]
    return None


def detect_output_conflicts(tasks: list[TaskSpec]) -> ConflictResult:
    """Detect output file conflicts among a set of tasks.

    Extracts --output from each task's command_args, resolves to canonical
    absolute paths, and partitions into parallel groups (no conflict) and
    serial chains (shared output file).

    Args:
        tasks: List of task specifications to check for conflicts.

    Returns:
        ConflictResult with parallel_groups, serial_chains, and warnings.
    """
    if not tasks:
        return ConflictResult(parallel_groups=[], serial_chains=[], warnings=[])

    # Tasks with a resolvable --output, grouped by canonical path
    path_groups: dict[str, list[TaskSpec]] = defaultdict(list)
    # Tasks without --output or with unresolvable paths (always parallel)
    no_conflict_tasks: list[TaskSpec] = []

    for task in tasks:
        raw_path = _extract_output_path(task.command_args)

        if raw_path is None:
            no_conflict_tasks.append(task)
            continue

        try:
            resolved = str(Path(raw_path).resolve())
        except OSError as exc:
            print(
                f"[DISPATCH WARN] Path resolution failed for task {task.task_id}: {exc}",
                file=sys.stderr,
            )
            no_conflict_tasks.append(task)
            continue

        path_groups[resolved].append(task)

    # Partition into parallel vs serial
    parallel_groups: list[list[TaskSpec]] = []
    serial_chains: list[list[TaskSpec]] = []
    warnings: list[str] = []

    for resolved_path, group in path_groups.items():
        if len(group) > 1:
            serial_chains.append(group)
            task_ids = [t.task_id for t in group]
            warnings.append(
                f"[DISPATCH WARN] Serializing tasks {task_ids} \u2014 shared output file: {resolved_path}"
            )
        else:
            parallel_groups.append(group)

    # Each no-conflict task is its own parallel group
    for task in no_conflict_tasks:
        parallel_groups.append([task])

    return ConflictResult(
        parallel_groups=parallel_groups,
        serial_chains=serial_chains,
        warnings=warnings,
    )
