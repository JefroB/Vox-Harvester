---
name: Software Engineering
tags: [always]
description: Core coding principles applied to every task.
---

# Software Engineering

Universal principles for writing maintainable software.

## Code Quality

- Keep functions short and focused on a single responsibility
- NEVER nest more than three levels of control flow
- Use descriptive variable names that reveal intent
- Prefer composition over inheritance
- Return early to reduce nesting depth
- MUST handle all error cases explicitly

## Testing Practices

- Write tests before fixing bugs to prevent regression
- Test behavior, not implementation details
- ALWAYS include edge cases: empty input, boundary values, null
- Use descriptive test names that explain the expected outcome
- Prefer integration tests for critical paths
