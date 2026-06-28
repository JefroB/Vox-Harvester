---
name: Documentation (docs/ Folder)
tags: [docs]
description: Standards for project-level documentation in the docs/ folder — usage guides, architecture, design rationale, and reference material.
---

# Documentation (docs/ Folder)

## Core Principle

The `docs/` folder is the single source of truth for understanding this project at a design and usage level. It serves both human developers joining the project and AI agents that need architectural context to make correct decisions.

## 1. What Belongs in docs/

### Required Documents

Every non-trivial project MUST have:

| Document | Purpose | Audience |
|---|---|---|
| `docs/README.md` | Index and overview — links to all other docs | Everyone |
| `docs/ARCHITECTURE.md` | System design, component relationships, data flow | Devs, agents |
| `docs/USAGE.md` | How to run, configure, and use the application | End users, new devs |

### Additional Documents (as needed)

| Document | When to create |
|---|---|
| `docs/<FEATURE>.md` | Feature has non-obvious design decisions or complex flow |
| `docs/API_REFERENCE.md` | Project exposes an API (REST, WebSocket, CLI) |
| `docs/DEPLOYMENT.md` | Non-trivial deployment steps or infrastructure |
| `docs/TROUBLESHOOTING.md` | Known issues with workarounds that aren't obvious |
| `docs/CONTRIBUTING.md` | Project accepts external contributions |

## 2. Document Structure

Every document in `docs/` should follow this pattern:

```markdown
# Title

Brief one-paragraph summary of what this document covers.

## Sections...

Content organized by topic, not chronologically.

## Related Documents

Links to other relevant docs (if any).
```

### Rules

- Start with a clear title and one-line purpose statement
- Use headers to create scannable structure
- Keep paragraphs short (3-5 sentences max)
- Use diagrams (ASCII or Mermaid) for data flow and architecture
- Link to source files when referencing specific implementations
- Date-stamp sections that describe temporary workarounds

## 3. Architecture Documentation

`docs/ARCHITECTURE.md` must cover:

1. **High-level overview** — what the system does in 2-3 sentences
2. **Component diagram** — major modules and how they connect
3. **Data flow** — how data moves through the system (request lifecycle)
4. **Key design decisions** — WHY things are structured this way, not just what they are
5. **Technology choices** — what's used and why it was chosen over alternatives
6. **Boundaries** — what each module is responsible for and what it explicitly is NOT

### Design Rationale

For every significant architectural choice, document:
- The decision made
- Alternatives that were considered
- Why this approach was chosen (constraints, tradeoffs)
- When it might need to be revisited

```markdown
## Audio Slicing Strategy

**Decision:** Post-input seeking (`-ss` after `-i` in ffmpeg)

**Alternatives considered:**
- Pre-input seeking (fast but imprecise for compressed formats)
- Pre-decode to PCM then slice (accurate but doubles storage)

**Why:** Millisecond accuracy is a hard requirement for speech dataset
creation. The CPU cost of decoding from start is acceptable given typical
audio lengths (3-15 minutes, not hours).

**Revisit when:** If we support videos >1 hour, pre-decoding to PCM
with indexed seeking may become necessary.
```

## 4. Usage Documentation

`docs/USAGE.md` must cover:

1. **Prerequisites** — what's needed before running (runtimes, tools, env vars)
2. **Installation** — step-by-step setup from fresh clone
3. **Running** — how to start the application (dev and production)
4. **Configuration** — all environment variables and config options with defaults
5. **Common workflows** — the 3-5 most common things a user does, explained step by step
6. **Troubleshooting** — known gotchas and their solutions

### Tone

- Write for someone who has never seen this project before
- Use concrete examples, not abstract descriptions
- Include actual commands they can copy-paste
- Note platform-specific differences (Windows vs Linux)

## 5. Keeping Docs Current

### Two READMEs — Both Must Stay Updated

This project has two README files with distinct roles:

| File | Role | Content |
|---|---|---|
| `README.md` (root) | Project introduction and quick-start | Brief overview, tech stack summary, quick-start commands, links into `docs/` |
| `docs/README.md` | Full developer handbook and docs index | Detailed architecture, user flows, resolved bugs, links to all other docs |

**Update rules:**
- When a new doc is added to `docs/`, add it to BOTH the root README's documentation section AND `docs/README.md`'s table of contents.
- When the tech stack changes, update BOTH READMEs.
- When user-facing features change, update the root README's "How It Works" section and `docs/README.md`'s detailed flow.
- The root README links to `docs/README.md` as the authoritative deep-dive. Never duplicate the full handbook content in the root.

### The Staleness Problem

Stale docs are worse than no docs — they actively mislead. Documentation MUST be treated as part of the implementation, not a separate chore.

### Update Triggers

| Event | Required doc action |
|---|---|
| New feature added | Add to ARCHITECTURE (if structural) + USAGE (if user-facing) |
| Feature removed | Remove from all docs, update README index |
| API changed | Update API_REFERENCE immediately |
| File/module renamed | Search docs for old name, update references |
| Design decision changed | Update rationale in ARCHITECTURE |
| Bug workaround added | Document in TROUBLESHOOTING or inline |
| Spec completed | Verify all docs still accurate, update as needed |

### Verification Checklist (end of spec)

Before a spec is marked complete:
- [ ] `docs/README.md` index links are all valid
- [ ] No doc references removed files, renamed functions, or deprecated approaches
- [ ] New user-facing features are documented in USAGE
- [ ] New architectural components are documented in ARCHITECTURE
- [ ] Design decisions are documented with rationale

## 6. Anti-Patterns

- ❌ Docs that describe aspirational features not yet implemented
- ❌ Copy-pasting code into docs without explanation (code should be in the repo, docs explain it)
- ❌ Docs with no clear audience — mixing user guides with implementation details
- ❌ Orphan docs not linked from README
- ❌ Version-specific instructions without noting the version they apply to
- ❌ Rewriting existing docs during a refactor without checking if the old content is still valid first

## 7. For Agentic Coders

When an agent completes implementation work:

1. **Check docs/README.md** — does the index still reflect reality?
2. **Check docs/ARCHITECTURE.md** — did you add/remove/rename a module?
3. **Check docs/USAGE.md** — did the user-facing behavior change?
4. **If yes to any** — update the relevant doc as part of the same task, not a follow-up

Agents should treat documentation updates as part of the definition of done, not a separate task to be filed for later.
