---
name: fallback-chain-pattern
tags: [code, error, fallback, strategy]
category: strategy-libraries
complexity: any
description: Multi-layer fallback resolution with warnings at each level
priority: 8
---

# Fallback Chain Pattern

## Pattern Overview

The fallback chain pattern implements multi-layer resolution: when the primary operation fails, the system doesn't immediately crash. Instead, it emits a warning describing what failed and what fallback is being attempted, then tries a secondary approach. If that also fails, another warning is emitted and a tertiary approach is tried. Only when ALL layers have been exhausted does the system raise a fatal error with an actionable message.

The key insight: **every layer transition must emit a warning with context**. This gives operators visibility into degraded behavior before a hard failure occurs. Silent fallbacks hide problems; loud fallbacks surface them early.

**Resolution order:**
1. Try primary → on failure: warn (what failed, what's next) → continue
2. Try secondary → on failure: warn (what failed, what's next) → continue
3. Try tertiary → on failure: raise fatal error with actionable message

## Working 3-Layer Example

```python
import sys
import warnings


def load_configuration(config_name: str) -> dict:
    """Load configuration using a 3-layer fallback chain.

    Attempts: remote config service → local config file → built-in defaults.
    Each fallback emits a warning with context about what failed and what
    is being attempted next.
    """
    # --- Layer 1: Primary (remote config service) ---
    try:
        config = fetch_from_remote_service(config_name)
        return config
    except ConnectionError as exc:
        warnings.warn(
            f"Primary config source failed: remote service unreachable "
            f"({exc}). Falling back to local config file.",
            RuntimeWarning,
            stacklevel=2,
        )

    # --- Layer 2: Secondary (local config file) ---
    try:
        config = read_local_config_file(config_name)
        return config
    except FileNotFoundError as exc:
        print(
            f"[WARN] Secondary config source failed: local file not found "
            f"({exc}). Falling back to built-in defaults.",
            file=sys.stderr,
        )

    # --- Layer 3: Tertiary (built-in defaults) ---
    try:
        config = get_builtin_defaults(config_name)
        return config
    except KeyError as exc:
        # All layers exhausted — fatal error with actionable message
        raise RuntimeError(
            f"FATAL: All config sources exhausted for '{config_name}'. "
            f"No built-in default exists ({exc}). "
            f"Action required: ensure the remote config service is running at "
            f"CONFIG_SERVICE_URL, or place a local config file at "
            f"~/.config/{config_name}.yaml, or add a default entry in "
            f"defaults.py for '{config_name}'."
        ) from exc
```

## Warning Format Guidelines

Each fallback level MUST emit a warning to stderr that includes:

1. **What failed** — name the source/operation and include the original error context
2. **What fallback is being attempted** — name the next layer explicitly
3. **The original error** — preserve the exception message or relevant detail

**Template:**
```
"{Layer N} failed: {what went wrong} ({original_error}). Falling back to {Layer N+1}."
```

**Use `warnings.warn()` or `print(..., file=sys.stderr)`:**
- `warnings.warn()` — preferred when callers may want to suppress/filter warnings programmatically
- `print(..., file=sys.stderr)` — preferred for operational visibility in scripts/services where warning filters might hide `warnings.warn()` output

**The fatal error (last layer) must be actionable:**
- State that all sources are exhausted
- List what the operator can do to fix the situation
- Include enough context to diagnose without reading source code

## Anti-Pattern: Skipping Intermediate Layers

### WRONG — Only first and last layer, no intermediate warnings

```python
def load_configuration_wrong(config_name: str) -> dict:
    """BAD: Skips intermediate fallbacks and warnings entirely."""
    try:
        return fetch_from_remote_service(config_name)
    except Exception:
        # Jumps straight to fatal error — no fallback attempts, no warnings
        raise RuntimeError(f"Failed to load config '{config_name}'")
```

**Problems with this approach:**
- No intermediate recovery — if the remote is down but a local file exists, the system crashes unnecessarily
- No warnings — operators have zero visibility that anything was attempted
- No actionable message — "Failed to load config" doesn't tell anyone what to do
- Brittle — a single transient failure becomes a hard crash

### CORRECT — Full chain with warnings at every transition

```python
def load_configuration_correct(config_name: str) -> dict:
    """GOOD: Full fallback chain with warnings at each level."""
    # Layer 1: Primary
    try:
        return fetch_from_remote_service(config_name)
    except ConnectionError as exc:
        warnings.warn(
            f"Primary failed: remote service unreachable ({exc}). "
            f"Falling back to local config file.",
            RuntimeWarning,
            stacklevel=2,
        )

    # Layer 2: Secondary
    try:
        return read_local_config_file(config_name)
    except FileNotFoundError as exc:
        print(
            f"[WARN] Secondary failed: local file not found ({exc}). "
            f"Falling back to built-in defaults.",
            file=sys.stderr,
        )

    # Layer 3: Tertiary
    try:
        return get_builtin_defaults(config_name)
    except KeyError as exc:
        raise RuntimeError(
            f"FATAL: All config sources exhausted for '{config_name}'. "
            f"No built-in default exists ({exc}). "
            f"Action required: ensure remote service is running, or create "
            f"~/.config/{config_name}.yaml, or add default in defaults.py."
        ) from exc
```

**The difference:** intermediate layers provide graceful degradation with full visibility. Operators see warnings in logs before the system fails hard, and the system stays up when lower-priority sources can satisfy the request.
