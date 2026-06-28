# Documentation Requirements

Documentation is a mandatory deliverable for every spec, not a follow-up task. Code without documentation is incomplete code.

## Why This Exists

This project is maintained by both a human developer and AI agents (cloud and local). Neither can rely on institutional memory:
- The human works across sessions and may not remember implementation details weeks later
- AI agents have no memory between sessions and rely entirely on what's written
- The local coder model generates code without project context beyond what's injected

Without documentation, every future interaction with the codebase starts with expensive re-discovery. Good docs make the whole system faster and cheaper.

## The Two Documentation Skills

| Skill | File | Scope |
|---|---|---|
| Code Comments | `.kiro/skills/code-comments.md` | Inline: docstrings, `@param`, module headers, explanatory comments |
| Documentation (docs/ Folder) | `.kiro/skills/docs-folder.md` | Project-level: architecture, usage guides, design rationale in `docs/` |

Both are tagged `docs` and auto-activate together on any documentation-related task. `code-comments` is also tagged `code` so it activates during any code generation.

## When Documentation Is Required

### Always (every code change)

- New exported functions get docstrings (code-comments skill)
- Modified functions get updated docstrings if behavior changed
- Non-obvious logic gets inline `// why` comments

### At Spec Completion

Before the final task of any spec is marked complete:

1. **Code comments** — all new/changed public APIs have docstrings
2. **docs/ updates** — if the spec changed architecture, user-facing behavior, or API surface:
   - Update `docs/ARCHITECTURE.md` for structural changes
   - Update `docs/USAGE.md` for user-facing changes
   - Update `docs/API_REFERENCE.md` for endpoint changes
   - Verify `docs/README.md` index links are valid
3. **Stale doc cleanup** — search docs/ for references to anything renamed or removed during the spec

### Local Coder Tasks

When delegating to the local model:
- Include `--tags code` (which activates `code-comments`) for any code generation
- Include `--tags docs` when the output is documentation itself
- The local model is responsible for generating docstrings as part of the code — review this during the generate-review-fix loop

## Enforcement

### In Spec Task Design

Spec tasks should include documentation as part of their acceptance criteria, not as separate "write docs" tasks at the end. Example:

```
- [ ] 2.3 Implement retry logic for Cobalt downloads
  - Add exponential backoff with jitter
  - Document retry parameters in function docstring
  - Update docs/ARCHITECTURE.md if retry strategy is architecturally significant
```

### In Code Review

Undocumented public APIs are flagged as incomplete during review. A change is not mergeable if:
- New exported functions lack docstrings
- Complex logic has no explanatory comments
- The change invalidates existing docs without updating them

### The "No Orphan Docs" Rule

- Every doc in `docs/` MUST be linked from `docs/README.md`
- If a doc isn't linked, it's invisible and will rot
- When creating a new doc, add it to the README index in the same commit

## What Good Looks Like

A well-documented spec completion:
1. Code has docstrings explaining *what* and *why* at every public boundary
2. `docs/ARCHITECTURE.md` reflects any new components or changed relationships
3. `docs/USAGE.md` tells a new user how to use any new features
4. No stale references exist in `docs/`
5. The README index is current

A poorly-documented spec completion:
1. Functions work but have no docstrings
2. Architecture changed but docs still describe the old design
3. New features exist but users wouldn't know how to use them from docs alone
4. Dead links in README to docs that were renamed or deleted
