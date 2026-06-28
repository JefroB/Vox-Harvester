---
name: Testing Strategy
tags: [code, test]
description: What to test, how to structure tests, mocking, test pyramid, red flags.
---

# Testing Strategy

## Core Principle

Tests prove behavior works and stays working. Write tests that give confidence to change code, not tests that break when you refactor internals.

## What to Test

### Always test:
- Public API contracts (inputs → expected outputs)
- Edge cases: empty inputs, null/undefined, boundary values, overflow
- Error paths: invalid input, network failures, missing files, permission denied
- State transitions: before/after side effects

### Skip testing:
- Private implementation details (test through the public interface)
- Third-party library internals (mock at the boundary)
- Trivial getters/setters with no logic

## Test Structure

Follow **Arrange-Act-Assert** (AAA):

```
// Arrange — set up preconditions
// Act — perform the action under test
// Assert — verify the outcome
```

One logical assertion per test. Multiple `assert` calls are fine if they verify one behavior.

## Naming

Test names should describe the behavior, not the implementation:
- Good: `rejects_empty_username`, `returns_cached_result_on_second_call`
- Bad: `test1`, `testFunction`, `it_works`

## Test Isolation

- Tests must not depend on each other or share mutable state
- Each test sets up its own preconditions and tears down after
- No reliance on execution order
- Use fresh instances, not global singletons

## Mocking & Stubbing

- Mock at system boundaries: network, filesystem, databases, external APIs
- Don't mock the thing you're testing
- Prefer fakes (in-memory implementations) over mocks when practical
- Keep mocks simple — if a mock needs complex logic, rethink the boundary

## Test Pyramid

Aim for:
- **Many unit tests** — fast, isolated, test logic
- **Some integration tests** — verify components work together
- **Few end-to-end tests** — prove critical user flows work

## When to Write Tests

- Before fixing a bug: write a test that reproduces it, then fix
- After implementing a feature: cover the happy path and primary edge cases
- When refactoring: ensure existing tests pass, add any missing coverage for the code being changed

## Red Flags

- Tests that pass when the implementation is obviously broken
- Tests that fail on unrelated changes (too coupled to internals)
- Tests that require a specific environment/OS to run
- Tests with no assertions
- Flaky tests (pass sometimes, fail sometimes) — fix or delete immediately
