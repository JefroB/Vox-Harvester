"""Orchestrator package for SubAgent-Coder wave execution and dispatch control."""

from orchestrator.checkpoint import CheckpointResult, run_checkpoint
from orchestrator.dispatch import DispatchResult, audit_wave_delegation, dispatch_task_graph
from orchestrator.hints import (
    accumulate_context_files,
    build_local_coder_args,
    should_skip_review,
    validate_and_process_hints,
)
from orchestrator.routing import (
    RoutingDecision,
    auto_assign_routing,
    check_ollama_reachable,
    enforce_routing,
)
from orchestrator.wave_controller import (
    TaskResult,
    WaveController,
    parse_legacy_parallel_field,
    resolve_effective_concurrency,
)

__all__ = [
    # Wave controller
    "TaskResult",
    "WaveController",
    "parse_legacy_parallel_field",
    "resolve_effective_concurrency",
    # Routing
    "RoutingDecision",
    "auto_assign_routing",
    "check_ollama_reachable",
    "enforce_routing",
    # Hints
    "accumulate_context_files",
    "build_local_coder_args",
    "should_skip_review",
    "validate_and_process_hints",
    # Checkpoint
    "CheckpointResult",
    "run_checkpoint",
    # Dispatch pipeline
    "DispatchResult",
    "audit_wave_delegation",
    "dispatch_task_graph",
]
