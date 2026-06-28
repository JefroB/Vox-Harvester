---
name: Software Engineering
tags: [always]
description: Core coding principles — naming, functions, architecture, error handling.
---

# Software Engineering Skill

## Purpose
Guide software development practices toward clean, maintainable, testable, and performant code.

## Design Principles

- **Simplicity first**: Solve the problem at hand. Avoid speculative abstractions or premature optimization.
- **Separation of concerns**: Each module/function should have one clear responsibility.
- **Explicit over implicit**: Prefer clear, readable code over clever tricks. Name things precisely.
- **Fail fast**: Validate inputs early. Surface errors close to their source.
- **Composition over inheritance**: Favor small, composable pieces over deep hierarchies.

## Code Quality

### Naming
- Use descriptive, intention-revealing names
- Functions: verb phrases (`calculateTotal`, `fetchUserById`)
- Booleans: question form (`isActive`, `hasPermission`)
- Constants: UPPER_SNAKE_CASE for true constants, camelCase for derived values
- Avoid abbreviations unless they are universally understood in context

### Functions
- Keep functions short and focused (one level of abstraction)
- Limit parameters (3 or fewer preferred; use an options object for more)
- Avoid side effects where possible; when unavoidable, make them obvious
- Return early to reduce nesting

### Error Handling
- Use typed errors or error codes, not bare strings
- Handle errors at the appropriate level (don't catch and ignore)
- Provide actionable error messages with context
- Distinguish between recoverable and unrecoverable errors

### Validation
- NEVER validate objects by counting keys/fields (e.g., `keys.length !== 17`). LLMs miscount.
- Always validate by checking each required key exists individually
- If a count check is truly needed, derive it from the authoritative list: `REQUIRED_FIELDS.length`, not a magic number
- Prefer exhaustive field checking over length assertions

### Testing
- Write tests that describe behavior, not implementation
- Follow Arrange-Act-Assert structure
- Test edge cases and error paths, not just happy paths
- Keep tests independent — no shared mutable state between tests

## Architecture Patterns

- Keep dependencies flowing in one direction (dependency inversion)
- Define clear boundaries between modules with explicit interfaces
- Use dependency injection for testability and flexibility
- Prefer pure functions and immutable data where practical
- Isolate I/O at the edges of your system

## Version Control

- Write atomic commits: one logical change per commit
- Use conventional commit messages: `type(scope): description`
- Keep PRs small and focused for easier review
- Branch from main, merge back to main — keep branches short-lived

## Performance

- Measure before optimizing — use profiling, not intuition
- Optimize the hot path, not everything
- Prefer algorithmic improvements over micro-optimizations
- Cache expensive computations; invalidate caches explicitly
- Be mindful of memory allocation in loops

## Security & Robustness

- Validate all external input (API responses, user input, file data)
- Never store secrets in code or version control
- Keep dependencies updated and audit for known vulnerabilities
- Treat external services as untrusted boundaries — validate response shapes
- Handle gracefully when state changes unexpectedly (e.g., resources deleted mid-operation)
