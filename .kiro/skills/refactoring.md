---
name: Refactoring
tags: [code, refactor]
description: When to refactor, safe patterns, code smells, small steps approach.
---

# Refactoring

## Core Principle

Refactoring improves code structure without changing behavior. It's maintenance, not feature work. Tests must pass before, during, and after.

## When to Refactor

### Good reasons:
- Code is hard to understand (takes more than 30 seconds to grasp a function)
- Adding a feature requires touching many unrelated files (high coupling)
- Same logic is duplicated in 3+ places
- A function does more than one thing
- Names no longer reflect what the code does
- Tests are brittle because they're coupled to implementation details

### Bad reasons:
- "I'd write it differently" (style preference, not a problem)
- It works fine but uses an older pattern
- To look busy / pad a PR
- Before understanding why the code was written that way

## Rules

### Never refactor without tests
- If there are no tests for the code you're changing, write them FIRST
- Run tests after every small change — refactor in tiny steps
- If tests break, you changed behavior (either the test or the refactor is wrong)

### One thing at a time
- Don't refactor and add features in the same commit
- Don't refactor and fix bugs in the same commit
- This keeps the git history clear: "refactor: X" means no behavior change

### Small steps
- Extract one function at a time
- Rename one thing at a time
- Move one file at a time
- Each step should be independently committable and passing

## Common Refactoring Moves

### Extract function
When a block of code does one logical thing, give it a name:
- Before: 15-line block inline
- After: `validateUserInput(data)` — now the caller reads at a higher level

### Rename
When a name is misleading, outdated, or vague:
- `data` → `userProfile`
- `process()` → `sendNotificationEmail()`
- `tmp` → `filteredResults`

### Inline
When an abstraction adds complexity without value:
- A function called only once that just wraps a single expression
- A variable that's used immediately and the expression is already clear

### Replace conditional with polymorphism
When a switch/if-else chain dispatches on type:
- Each case becomes a class/method that handles its own behavior
- Only worth it when the conditional appears in multiple places

### Move to boundary
When business logic is mixed with I/O:
- Extract the pure logic into a function that takes data and returns data
- Keep I/O (database, network, filesystem) at the edges

## Code Smells (Triggers for Refactoring)

- **Long function** (>30 lines) — extract sub-functions
- **Long parameter list** (>4 params) — group into an object
- **Duplicated logic** (3+ copies) — extract and share
- **Deep nesting** (>3 levels) — early returns, extract functions
- **Comments explaining "what"** — rename to make code self-explanatory
- **Dead code** — delete it (version control remembers)
- **God object/function** — does too many things, split by responsibility

## Anti-Patterns

- ❌ "Big bang" refactors that change everything at once
- ❌ Refactoring without running tests between steps
- ❌ Creating abstractions for one use case ("in case we need it later")
- ❌ Moving code around without improving clarity or reducing coupling
- ❌ Refactoring code you don't understand — understand it first
- ❌ Mixing refactoring with feature changes in one PR
