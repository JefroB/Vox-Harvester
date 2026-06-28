---
name: Documentation Standards
tags: [code, docs]
description: Rules for code documentation, docstrings, and maintaining the docs/ folder.
---

# Documentation Standards

## Core Principle

Code is not complete until it is documented. Documentation is a first-class deliverable, not an afterthought.

## 1. Code Documentation

Every public function, method, and class MUST have a doc comment explaining:

- **What** it does (one-line summary)
- **Parameters** with types and descriptions
- **Returns** with type and description
- **Throws** (if applicable)

### Style

```typescript
/**
 * Parse a configuration file and return validated settings.
 *
 * @param filePath - Absolute path to the config file
 * @param defaults - Optional fallback values for missing keys
 * @returns Validated configuration object
 * @throws ConfigError if the file is malformed or missing required fields
 */
export function parseConfig(filePath: string, defaults?: Partial<Config>): Config {
```

### Rules

- Unexported helpers need at minimum a one-line summary.
- If a function's purpose is not obvious from its name, it needs a doc comment regardless of visibility.
- Do NOT write comments that merely restate the function name. Add value — explain *why*, edge cases, or non-obvious behavior.
- Use `@internal` tag for functions that are exported only for testing.

## 2. Documentation Location

All project-level documentation lives in the `docs/` folder at the repository root.

### What belongs in `docs/`

- Architecture and design documents
- Setup and workflow guides
- Development workflow references
- Feature design notes and future plans

### What does NOT belong in `docs/`

- Auto-generated API docs (use a tool like TypeDoc, output to a separate folder)
- Scripts or code (those go in `scripts/` or `src/`)
- Temporary notes or scratch files

## 3. Spec Completion Checklist

A spec task is NOT complete until all of the following are satisfied:

1. **New code is documented** — Every new function/class/method has a docstring.
2. **Changed code is re-documented** — If you modify a function's behavior, update its docstring to match.
3. **Outdated docs are updated or removed** — If a feature changes or is removed, find and update any references in `docs/`. Remove docs that describe things that no longer exist.
4. **New features get a docs entry** — If the feature is significant enough to affect how someone uses or understands the project, add or update the relevant doc in `docs/`.

## 4. Documentation Hygiene

### When modifying code

- Search `docs/` for references to the code you changed.
- If file paths, function names, or behaviors changed, update the docs.
- If a doc references something that no longer exists, remove that section or the entire doc.

### When completing a spec

Before marking the final task complete, verify:
- `docs/` contains no references to removed files, renamed functions, or deprecated approaches.
- New public APIs introduced by the spec are documented in both code (docstrings) and project docs (if architecturally significant).

### When reviewing code

Flag undocumented public functions as incomplete. A PR/change is not ready to merge if public interfaces lack docstrings.

## 5. Anti-Patterns

- ❌ Empty or placeholder comments: `/** TODO: document this */`
- ❌ Comments that just repeat the function signature: `/** Set the volume. */` on `setVolume()`
- ❌ Stale comments that describe old behavior after a refactor
- ❌ Documentation that references files or features that have been removed
- ❌ Leaving `docs/` untouched after a major architectural change

## 6. Good Patterns

- ✅ Explain *why* a function exists, not just *what* it does
- ✅ Document edge cases and constraints
- ✅ Keep docs concise — link to other docs rather than duplicating content
- ✅ Use the README as the index — if a doc isn't linked there, it's invisible
- ✅ Delete docs that have served their purpose (resolved issue trackers, completed migration guides)
