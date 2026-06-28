---
inclusion: auto
---

# Task Delegation Tags — Mandatory Annotations

## Rule: Every Sub-Task MUST Have a Delegation Annotation

When generating or updating a `tasks.md` file in `.kiro/specs/`, every sub-task (lines starting with `- [ ]` under a parent task) MUST end with exactly one of:

1. **Local coder delegation hint:**
   ```
   [local-coder: --tags <tag1> <tag2> ... --complexity <simple|complex> --context <file1> <file2>]
   ```

2. **Cloud-only annotation (when delegation is inappropriate):**
   ```
   [cloud-only: <brief reason>]
   ```

## When to Use Each

### Use `[local-coder: ...]` when:
- The task is a single function/module implementation with clear spec
- The task is writing tests (property-based or unit)
- The task creates boilerplate, templates, or seed files
- The task is straightforward and self-contained

### Use `[cloud-only: ...]` when:
- The task composes multiple modules or requires architectural understanding
- The task modifies existing complex code (e.g., CLI integration into an existing script)
- The task writes prose documentation that references actual codebase structure
- The task is a checkpoint or verification step
- The task requires reading and understanding 3+ existing files to produce correct output

## Tag Selection Guide

| Task type | Tags |
|---|---|
| Implementation (general) | `--tags code` |
| Implementation + API | `--tags code api` |
| Implementation + security-sensitive | `--tags code security` |
| Property-based tests | `--tags code test` |
| Unit/integration tests | `--tags code test` |
| Seed templates / boilerplate | `--tags code` |
| Refactoring | `--tags code refactor` |

## Complexity Selection Guide

| Condition | Complexity | Routes to |
|---|---|---|
| Single function, clear inputs/outputs, <100 lines expected | `simple` | qwen2.5-coder:7b |
| Multiple functions, error handling, moderate reasoning, set logic | `complex` | qwen3-coder:30b |
| Multi-module composition, architectural decisions, reading 3+ existing files | (cloud-only) | Kiro |

### Key distinction: `simple` vs `complex`
- **simple**: the task can be described in one sentence and produces a single function/class with obvious logic (loops, filters, data transforms)
- **complex**: the task involves error recovery, multiple code paths, set operations, composite sorting, or partial-result handling — but is still self-contained within one module

## Context Selection Guide

- `--context` should list the PRIMARY file(s) being implemented or tested against
- Maximum 5 context files (more than 5 = probably cloud-only)
- Always include the file being tested for test tasks
- Always include the file being extended for implementation tasks

## Edit Target Annotation (MANDATORY for edit-existing-code tasks)

When a task modifies existing code (not creating a new file), you MUST include `--output <file>` and `--scope <symbol-or-lines>` in the annotation. These values come from codesearch at spec generation time.

**Format:**
```
[local-coder: --tags code --complexity complex --output src/auth.py --scope "validate_token,refresh_token" --context src/auth.py]
```

**Rules:**
1. Use `codesearch get-definition` or `codesearch search-content` to find the exact file and line range BEFORE writing the task.
2. `--output` = the file being edited
3. `--scope` = comma-separated symbol names or line ranges (e.g., `"MyClass.method"` or `"lines 45-80"`)
4. `--context` should include the same file (so the model sees the current state)

**Example annotations for edit tasks:**
```
- [ ] 2.1 Add --task-id flag to argument parser [local-coder: --tags code --complexity simple --output .kiro/scripts/local_coder.py --scope "main,parser" --context .kiro/scripts/local_coder.py]
- [ ] 2.2 Replace uuid4() calls with resolved task ID [cloud-only: requires finding 4 locations and understanding control flow]
- [ ] 3.1 Add retry logic to call_ollama [local-coder: --tags code --complexity complex --output .kiro/scripts/local_coder.py --scope "call_ollama" --context .kiro/scripts/local_coder.py]
```

**Do NOT omit --output and --scope for edit tasks.** Without them, the local coder generates a full file instead of a targeted edit, and the result database can't track which files were modified.

## Validation

A valid tasks.md has ZERO sub-tasks without one of these annotations. If you generate a tasks.md and any sub-task lacks an annotation, you have made an error — go back and add it.

Parent-level tasks (top-level numbered items like `- [ ] 1. Create the module`) do NOT need annotations — only their sub-tasks do.

Checkpoint tasks (e.g., "Ensure all tests pass") use: `[cloud-only: checkpoint]`
