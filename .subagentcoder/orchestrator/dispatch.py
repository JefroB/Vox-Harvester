"""Unified dispatch pipeline for the SubAgent-Coder orchestrator.

Ties together wave execution control, routing assignment/enforcement, hints
validation/processing, and inline checkpoint execution into a single
`dispatch_task_graph` async function.

This module is the top-level entry point for executing a parsed task graph
end-to-end, handling:
- Wave-by-wave sequential processing
- Per-wave concurrency control via WaveController
- Auto-routing assignment for tasks without explicit routing
- Hints validation and context file accumulation
- Inline checkpoint execution (no subagent spawn)
- Implementation task dispatch with routing enforcement
- Failure propagation: wave failure halts subsequent waves

All errors use [ERROR] prefix to stderr.
All warnings use [WARN] prefix to stderr.

Requirements: 1.1–1.6, 2.1–2.6, 3.1–3.9, 4.1–4.7
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from local_coder.conflict_detector import (
    ConflictResult,
    TaskSpec,
    detect_output_conflicts,
)
from local_coder.execution_hook import (
    audit_delegation_compliance,
    inject_delegation_prompt,
)
from models.task_graph import ExecutionConfig, HintsPayload, WaveConfig
from orchestrator.checkpoint import run_checkpoint
from orchestrator.hints import (
    accumulate_context_files,
    build_local_coder_args,
    validate_and_process_hints,
)
from orchestrator.routing import (
    auto_assign_routing,
    check_ollama_reachable,
    enforce_routing,
)
from orchestrator.wave_controller import (
    TaskResult,
    WaveController,
    parse_legacy_parallel_field,
)


@dataclass
class DispatchResult:
    """Overall result of dispatching an entire task graph.

    Attributes:
        success: True if all waves completed without failure.
        wave_results: List of per-wave result lists.
        halted_at_wave: Index of the wave that caused a halt, or None if all passed.
        failure_report: Human-readable failure report, or None on success.
    """

    success: bool
    wave_results: list[list[TaskResult]] = field(default_factory=list)
    halted_at_wave: int | None = None
    failure_report: str | None = None


def _parse_task_metadata(task_id: str, task_registry: dict[str, dict]) -> dict[str, Any]:
    """Extract task metadata from the task registry.

    Args:
        task_id: The task identifier to look up.
        task_registry: Dictionary mapping task_id to metadata dicts.

    Returns:
        Metadata dict with keys: type, routing, hints, command, description.
        Defaults are applied for missing fields.
    """
    meta = task_registry.get(task_id, {})
    return {
        "type": meta.get("type", "implementation"),
        "routing": meta.get("routing", "auto"),
        "hints": meta.get("hints"),
        "command": meta.get("command"),
        "description": meta.get("description", ""),
    }


def _extract_output_from_metadata(task_id: str, metadata: dict[str, Any]) -> str | None:
    """Extract the output file path from task metadata.

    Checks for an explicit 'output' field in metadata. If not present,
    returns None (task has no known output file target).

    Args:
        task_id: The task identifier.
        metadata: Task metadata dict.

    Returns:
        Output file path string, or None if not specified.
    """
    return metadata.get("output")


def _build_task_specs_for_wave(
    task_ids: list[str], task_registry: dict[str, dict]
) -> list[TaskSpec]:
    """Build TaskSpec objects for conflict detection from wave tasks.

    Only includes tasks that have an identifiable --output target.
    Tasks without output paths are excluded (they cannot conflict).

    Args:
        task_ids: List of task identifiers in the wave.
        task_registry: Dictionary mapping task_id to metadata dicts.

    Returns:
        List of TaskSpec objects with command_args containing --output.
    """
    specs: list[TaskSpec] = []
    for task_id in task_ids:
        meta = task_registry.get(task_id, {})
        output_path = meta.get("output")
        if output_path:
            # Build a command_args list that includes --output for detection
            specs.append(TaskSpec(task_id=task_id, command_args=["--output", output_path]))
        else:
            # Tasks without --output are always safe to parallelize
            specs.append(TaskSpec(task_id=task_id, command_args=[]))
    return specs


def _apply_conflict_detection(
    wave_config: WaveConfig,
    task_registry: dict[str, dict],
) -> tuple[list[list[str]], list[str]]:
    """Detect output conflicts and partition wave tasks.

    Inspects --output targets of all tasks in the wave, detects conflicts,
    and returns partitioned groups for parallel and serial execution.

    Emits warnings to stderr for any serialized task groups.

    Args:
        wave_config: The wave configuration with task list.
        task_registry: Dictionary mapping task_id to metadata dicts.

    Returns:
        Tuple of (parallel_task_groups, serial_task_chains):
        - parallel_task_groups: list of task_id lists safe to run concurrently.
        - serial_task_chains: list of task_id lists that must run sequentially.
    """
    task_ids = wave_config.tasks
    if not task_ids:
        return [], []

    # Build TaskSpec objects for conflict detection
    task_specs = _build_task_specs_for_wave(task_ids, task_registry)

    # Run conflict detection
    result: ConflictResult = detect_output_conflicts(task_specs)

    # Emit warnings to stderr
    for warning in result.warnings:
        print(warning, file=sys.stderr)

    # Extract task_id lists from the groups
    parallel_groups = [
        [task.task_id for task in group] for group in result.parallel_groups
    ]
    serial_chains = [
        [task.task_id for task in chain] for chain in result.serial_chains
    ]

    return parallel_groups, serial_chains


async def _dispatch_implementation_task(
    task_id: str,
    metadata: dict[str, Any],
    project_root: Path,
    ollama_reachable: bool,
) -> TaskResult:
    """Dispatch a single implementation task with routing and hints.

    Performs:
    1. Auto-assigns routing if routing == "auto" using heuristics.
    2. Validates and processes hints.
    3. Enforces routing (with fallback logic for local routing).
    4. Accumulates context files if present in hints.
    5. Builds local coder args if routing to local.
    6. Injects mandatory delegation prompt for [local-coder: ...] tasks.

    Args:
        task_id: Task identifier.
        metadata: Task metadata dict (type, routing, hints, description).
        project_root: Project root path for context file resolution.
        ollama_reachable: Whether Ollama responded to health check.

    Returns:
        TaskResult representing the dispatch outcome.
    """
    routing = metadata["routing"]
    description = metadata["description"]
    raw_hints = metadata["hints"]

    # Step 1: Auto-assign routing if "auto"
    if routing == "auto":
        routing = auto_assign_routing(description)
        if routing != "auto":
            print(
                f"[WARN] dispatch: Auto-assigned routing '{routing}' for task '{task_id}'",
                file=sys.stderr,
            )

    # Step 2: Validate and process hints
    hints_payload: HintsPayload | None = None
    if raw_hints is not None:
        hints_payload, hint_warnings = validate_and_process_hints(raw_hints)
        # Warnings already emitted to stderr by validate_and_process_hints

    # Step 3: Estimate tokens for routing enforcement
    # Base estimate: description tokens + overhead
    estimated_tokens = len(description) // 4 + 500  # base overhead

    # Step 4: Accumulate context files if present
    context_contents: list[str] = []
    if hints_payload and hints_payload.context_files:
        context_contents, ctx_warnings = accumulate_context_files(
            hints_payload.context_files, project_root
        )
        # Add context tokens to estimate
        for content in context_contents:
            estimated_tokens += len(content) // 4

    # Step 5: Enforce routing with fallback logic
    routing_decision = enforce_routing(routing, estimated_tokens, ollama_reachable)

    if routing_decision.override_reason:
        print(
            f"[WARN] dispatch: Routing override for task '{task_id}': "
            f"{routing_decision.override_reason} — falling back to cloud",
            file=sys.stderr,
        )

    # Step 6: Build local coder args if routing to local
    local_coder_args: list[str] = []
    if routing_decision.target == "local" and hints_payload:
        local_coder_args, should_use_local = build_local_coder_args(
            hints_payload, estimated_tokens
        )
        # If preferLocalCoder hint says fallback to cloud, respect it
        if should_use_local is False:
            print(
                f"[WARN] dispatch: preferLocalCoder hint triggered cloud fallback "
                f"for task '{task_id}' (prompt too large)",
                file=sys.stderr,
            )
            routing_decision = type(routing_decision)(
                target="cloud",
                override_reason="preferLocalCoder threshold exceeded",
            )

    # Step 7: Inject delegation prompt for [local-coder: ...] annotated tasks
    dispatch_description = inject_delegation_prompt(description)

    return TaskResult(
        task_id=task_id,
        success=True,
        output={
            "routing": routing_decision.target,
            "override_reason": routing_decision.override_reason,
            "hints": hints_payload,
            "context_files_loaded": len(context_contents),
            "local_coder_args": local_coder_args,
            "estimated_tokens": estimated_tokens,
            "delegation_enforced": dispatch_description != description,
            "dispatch_description": dispatch_description,
        },
    )


async def _dispatch_checkpoint_task(
    task_id: str,
    metadata: dict[str, Any],
    project_root: Path,
) -> TaskResult:
    """Execute a checkpoint task inline without spawning a subagent.

    Args:
        task_id: Task identifier.
        metadata: Task metadata dict (must contain 'command').
        project_root: Project root for command execution.

    Returns:
        TaskResult reflecting checkpoint success or failure.
    """
    command = metadata.get("command")

    result = run_checkpoint(command, project_root)

    if result.success:
        return TaskResult(
            task_id=task_id,
            success=True,
            output={
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
                "output_lines": len(result.output.splitlines()) if result.output else 0,
            },
        )
    else:
        # Report failure with error details
        error_msg = result.error_message or f"Checkpoint failed with exit code {result.exit_code}"
        print(error_msg, file=sys.stderr)

        return TaskResult(
            task_id=task_id,
            success=False,
            error=error_msg,
            output=result.output,
        )


async def dispatch_task_graph(
    task_graph: dict,
    project_root: Path,
    config: ExecutionConfig | None = None,
) -> DispatchResult:
    """Execute a full task graph through the unified dispatch pipeline.

    Parses the task graph into waves, then processes each wave sequentially:
    1. Creates a WaveController with the wave config and global config.
    2. For each task in the wave:
       - Checkpoint tasks are executed inline via run_checkpoint().
       - Implementation tasks go through routing + hints + dispatch.
    3. On wave failure, halts subsequent waves and reports.

    Args:
        task_graph: Dictionary with "waves" (list of raw wave dicts) and
            "tasks" (dict mapping task_id to metadata). The "waves" list
            is processed in order; each wave dict is parsed via
            parse_legacy_parallel_field.
        project_root: The project root directory for checkpoint execution
            and context file resolution.
        config: Optional global execution config. If execution_mode is
            "sequential", all waves execute tasks one at a time.

    Returns:
        DispatchResult summarizing the overall execution outcome.
    """
    raw_waves = task_graph.get("waves", [])
    task_registry = task_graph.get("tasks", {})

    if not raw_waves:
        return DispatchResult(success=True)

    # Pre-check Ollama reachability once (avoid per-task latency)
    ollama_reachable = check_ollama_reachable(timeout=10.0)
    if not ollama_reachable:
        print(
            "[WARN] dispatch: Ollama unreachable — all local-routed tasks will fall back to cloud",
            file=sys.stderr,
        )

    all_wave_results: list[list[TaskResult]] = []

    for wave_index, raw_wave in enumerate(raw_waves):
        # Parse wave config (handles legacy "parallel": false alias)
        try:
            wave_config = parse_legacy_parallel_field(raw_wave)
        except (ValueError, TypeError) as e:
            error_msg = f"[ERROR] dispatch: Failed to parse wave {wave_index}: {e}"
            print(error_msg, file=sys.stderr)
            return DispatchResult(
                success=False,
                wave_results=all_wave_results,
                halted_at_wave=wave_index,
                failure_report=error_msg,
            )

        # Create wave controller
        controller = WaveController(wave_config, config)

        # Define the dispatch function for this wave
        async def dispatch_fn(task_id: str) -> TaskResult:
            metadata = _parse_task_metadata(task_id, task_registry)
            task_type = metadata["type"]

            if task_type == "checkpoint":
                return await _dispatch_checkpoint_task(
                    task_id, metadata, project_root
                )
            else:
                # Default: implementation
                return await _dispatch_implementation_task(
                    task_id, metadata, project_root, ollama_reachable
                )

        # --- Conflict Detection (Req 5.1–5.5) ---
        # Before dispatching parallel waves, detect output file conflicts
        # and serialize conflicting task groups while dispatching
        # non-conflicting groups in parallel.
        effective_concurrency = controller.effective_concurrency
        has_parallel_tasks = effective_concurrency > 1 and len(wave_config.tasks) > 1

        if has_parallel_tasks:
            parallel_groups, serial_chains = _apply_conflict_detection(
                wave_config, task_registry
            )

            if serial_chains:
                # We have conflicts — execute in phases:
                # Phase 1: Dispatch all non-conflicting tasks in parallel
                # Phase 2: Execute each serial chain sequentially
                wave_results: list[TaskResult] = []

                # Phase 1: parallel groups (no conflicts among themselves)
                if parallel_groups:
                    parallel_task_ids = [
                        tid for group in parallel_groups for tid in group
                    ]
                    parallel_wave = WaveConfig(
                        id=f"{wave_config.id}_parallel",
                        concurrency="parallel",
                        tasks=parallel_task_ids,
                    )
                    parallel_controller = WaveController(parallel_wave, config)
                    try:
                        parallel_results = await parallel_controller.execute(dispatch_fn)
                        wave_results.extend(parallel_results)
                    except Exception as e:
                        error_msg = (
                            f"[ERROR] dispatch: Wave {wave_index} parallel phase failed: {e}"
                        )
                        print(error_msg, file=sys.stderr)
                        return DispatchResult(
                            success=False,
                            wave_results=all_wave_results,
                            halted_at_wave=wave_index,
                            failure_report=error_msg,
                        )

                # Phase 2: serial chains (conflicting tasks run sequentially)
                for chain in serial_chains:
                    serial_wave = WaveConfig(
                        id=f"{wave_config.id}_serial",
                        concurrency="sequential",
                        tasks=chain,
                    )
                    serial_controller = WaveController(serial_wave, config)
                    try:
                        serial_results = await serial_controller.execute(dispatch_fn)
                        wave_results.extend(serial_results)
                    except Exception as e:
                        error_msg = (
                            f"[ERROR] dispatch: Wave {wave_index} serial chain failed: {e}"
                        )
                        print(error_msg, file=sys.stderr)
                        return DispatchResult(
                            success=False,
                            wave_results=all_wave_results,
                            halted_at_wave=wave_index,
                            failure_report=error_msg,
                        )

                    # Check serial chain for failures — halt on failure
                    chain_failures = [r for r in serial_results if not r.success]
                    if chain_failures:
                        first_failure = chain_failures[0]
                        report = (
                            f"[ERROR] dispatch: Task '{first_failure.task_id}' "
                            f"failed in serialized chain (wave {wave_index})."
                        )
                        if first_failure.error:
                            report += f"\n  Error: {first_failure.error}"
                        print(report, file=sys.stderr)
                        all_wave_results.append(wave_results)
                        return DispatchResult(
                            success=False,
                            wave_results=all_wave_results,
                            halted_at_wave=wave_index,
                            failure_report=report,
                        )
            else:
                # No conflicts detected — execute normally
                try:
                    wave_results = await controller.execute(dispatch_fn)
                except Exception as e:
                    error_msg = f"[ERROR] dispatch: Wave {wave_index} execution failed: {e}"
                    print(error_msg, file=sys.stderr)
                    return DispatchResult(
                        success=False,
                        wave_results=all_wave_results,
                        halted_at_wave=wave_index,
                        failure_report=error_msg,
                    )
        else:
            # Sequential or single-task wave — no conflict detection needed
            try:
                wave_results = await controller.execute(dispatch_fn)
            except Exception as e:
                error_msg = f"[ERROR] dispatch: Wave {wave_index} execution failed: {e}"
                print(error_msg, file=sys.stderr)
                return DispatchResult(
                    success=False,
                    wave_results=all_wave_results,
                    halted_at_wave=wave_index,
                    failure_report=error_msg,
                )

        all_wave_results.append(wave_results)

        # Check for failures — halt subsequent waves if any task failed
        # First check WaveController's built-in failure report (for bounded waves)
        failure_report = controller.failure_report()
        if failure_report:
            print(failure_report, file=sys.stderr)
            return DispatchResult(
                success=False,
                wave_results=all_wave_results,
                halted_at_wave=wave_index,
                failure_report=failure_report,
            )

        # Also check individual results for failures (parallel waves don't
        # set the controller's _failed flag, but we still halt on failure)
        failed_results = [r for r in wave_results if not r.success]
        if failed_results:
            first_failure = failed_results[0]
            report = (
                f"[ERROR] dispatch: Task '{first_failure.task_id}' failed in wave {wave_index}."
            )
            if first_failure.error:
                report += f"\n  Error: {first_failure.error}"
            print(report, file=sys.stderr)
            return DispatchResult(
                success=False,
                wave_results=all_wave_results,
                halted_at_wave=wave_index,
                failure_report=report,
            )

    return DispatchResult(
        success=True,
        wave_results=all_wave_results,
    )


def audit_wave_delegation(
    wave_results: list[TaskResult],
    task_registry: dict[str, dict],
) -> list[dict[str, str]]:
    """Post-execution audit: check all wave results for delegation compliance.

    For each task that has a [local-coder: ...] annotation in its description,
    verifies that the subagent output contains evidence of local_coder.py
    execution. Returns a list of violations.

    This is the orchestrator-level implementation of Option A from the
    enforcement changes plan.

    Args:
        wave_results: List of TaskResult from the wave execution.
        task_registry: Dictionary mapping task_id to metadata dicts
            (must include "description" field).

    Returns:
        List of violation dicts with keys:
        - task_id: The task that was bypassed
        - reason: Human-readable explanation of the violation
        - suggested_action: What the orchestrator should do (re-queue, flag, etc.)
    """
    violations: list[dict[str, str]] = []

    for result in wave_results:
        if not result.success:
            # Failed tasks are not auditable — they didn't complete
            continue

        task_id = result.task_id
        meta = task_registry.get(task_id, {})
        description = meta.get("description", "")

        # Only audit tasks with [local-coder: ...] annotation
        from local_coder.execution_hook import has_local_coder_annotation

        if not has_local_coder_annotation(description):
            continue

        # Extract subagent output text for compliance check
        subagent_output = ""
        if isinstance(result.output, dict):
            # The dispatch_description contains what was sent; we need the
            # subagent's response. If the output dict has a "subagent_response"
            # field, use it. Otherwise check for stringified output.
            subagent_output = str(result.output.get("subagent_response", ""))
            if not subagent_output:
                subagent_output = str(result.output)
        elif isinstance(result.output, str):
            subagent_output = result.output

        compliant, reason = audit_delegation_compliance(description, subagent_output)

        if not compliant:
            violations.append({
                "task_id": task_id,
                "reason": reason or "Unknown delegation violation",
                "suggested_action": "re-queue with stronger enforcement or mark as delegation-bypassed",
            })
            print(
                f"[ERROR] dispatch: DELEGATION BYPASS detected for task '{task_id}': {reason}",
                file=sys.stderr,
            )

    return violations
