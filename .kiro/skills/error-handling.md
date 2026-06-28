---
name: Error Handling
tags: [code]
description: Error categories, patterns, logging, fail-fast, anti-patterns.
---

# Error Handling

## Core Principle

Errors are data, not surprises. Handle them explicitly, surface them clearly, and never let them disappear silently.

## Error Categories

### Recoverable (expected)
- Invalid user input → validate and return helpful message
- Network timeout → retry with backoff, then fail gracefully
- File not found → check existence first, or catch and provide guidance
- Rate limited → wait and retry

### Unrecoverable (unexpected)
- Out of memory → crash cleanly, let the process manager restart
- Corrupted state → log context, abort operation, don't continue on broken data
- Missing critical config → fail on startup, not at runtime

## Rules

### Catch at the right level
- Handle errors where you can actually DO something about them
- Don't catch just to re-throw with less information
- Let unexpected errors propagate to a top-level handler

### Never swallow errors
- `catch (e) {}` is almost always a bug
- At minimum: log the error, then decide (retry, propagate, or degrade)
- Silent failures are the hardest bugs to diagnose

### Fail fast
- Validate early: check preconditions at function entry
- If state is invalid, error immediately — don't continue and corrupt further
- Prefer crashing over producing wrong results

### Error messages
- Include WHAT went wrong, WHERE (context), and ideally WHY or HOW to fix
- Bad: `"Error"`, `"Something went wrong"`, `"null"`
- Good: `"Failed to read config at /path/to/file: permission denied"`
- Internal errors can be verbose; user-facing errors should be helpful without leaking internals

## Patterns

### Return errors explicitly (Go/Rust style)
- Functions return `(result, error)` or `Result<T, E>`
- Caller must handle the error — can't accidentally ignore it

### Typed/custom errors
- Define error types for your domain: `ConfigError`, `AuthError`, `ValidationError`
- Include machine-readable codes alongside human-readable messages
- Allows callers to handle specific errors differently

### Error boundaries
- Catch all errors at system boundaries (API handlers, event listeners, job runners)
- Log with full context, return safe response to the caller
- Prevent one failure from cascading through the system

## Logging Errors

- Log the full error (message + stack trace + context) at the point of handling
- Include: timestamp, operation being performed, relevant identifiers
- Don't log the same error multiple times as it propagates up
- Distinguish error levels: debug (expected), warn (degraded), error (broken)

## Anti-Patterns

- ❌ `try { ... } catch (e) { /* TODO */ }`
- ❌ Returning `null` to signal an error (caller can't distinguish from valid null)
- ❌ Throwing strings instead of error objects
- ❌ Catching broad exception types when you only handle specific ones
- ❌ Retry loops with no backoff or max-attempt limit
- ❌ Logging errors without context (just the message, no stack, no input)
