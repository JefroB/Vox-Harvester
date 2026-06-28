# Architecture

## System Overview

SubAgent-Coder is a hybrid AI coding workflow that combines a local GPU (Ollama) for code generation with a cloud model (Kiro) for review and quality assurance, using a local Gitea server for version control.

```
┌─────────────────────────────────────────────────────────┐
│                        USER                              │
│                  "Build feature X"                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   KIRO (Cloud)                            │
│  • Orchestrator / Lead Architect                         │
│  • Selects model + skills + tags                         │
│  • Reviews all output                                    │
│  • Fixes bugs the local model misses                     │
│  • Manages git workflow                                  │
└──────┬───────────────────────────────────┬──────────────┘
       │ Delegates generation              │ Reviews output
       ▼                                   ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│  local_coder.py      │    │  CodeSearch CLI               │
│  (Orchestrator)      │    │  • Token-efficient inspection │
│  • Selects model     │    │  • Symbol search              │
│  • Injects skills    │    │  • Content grep               │
│  • Routes by task    │    │  • Module summaries           │
└──────┬───────────────┘    └──────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                OLLAMA (Local GPU)                          │
│  RTX 5070 (12GB VRAM)                                    │
│                                                          │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────┐  │
│  │ qwen2.5-coder:7b│ │ qwen3-coder:30b  │ │ qwen3:8b │  │
│  │ (fast/simple)   │ │ (heavy/complex)  │ │ (prose)  │  │
│  └─────────────────┘ └──────────────────┘ └──────────┘  │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                    GITEA (Local)                           │
│  http://192.168.1.25:3000                                │
│                                                          │
│  main ─────────── Production (Kiro-approved)             │
│  local-dev ─────── Subagent workspace                    │
└──────────────────────────────────────────────────────────┘
```

## Component Roles

| Component | Role | Location |
|---|---|---|
| Kiro | Orchestrator, reviewer, fixer | Cloud (Bedrock) |
| local_coder.py | Model router, skill injector, API caller | `.kiro/scripts/` |
| Ollama | Inference engine | localhost:11434 |
| CodeSearch | Token-efficient code inspection | pipx (`codesearch` CLI) |
| Gitea | Version control, branch isolation | 192.168.1.25:3000 |
| Skills | Coding standards injected into subagent | `.kiro/skills/` |
| Steering | Kiro behavior configuration | `.kiro/steering/` |
| Hooks | Automated triggers | `.kiro/hooks/` |

## Data Flow

### Generation Flow

1. User requests a feature
2. Kiro evaluates complexity (simple/complex/prose)
3. Kiro selects relevant tags → script selects matching skills
4. `local_coder.py` builds system prompt (base + skills) and task prompt
5. Script calls Ollama API with the selected model
6. Response comes back → script strips markdown fences → writes to file
7. Script logs token savings to CodeSearch DB

### Review Flow

1. Kiro runs `codesearch reindex-files <file>` (or watcher auto-indexes)
2. Kiro inspects via `codesearch module-summary`, `get-symbol-code`, `search-content`
3. Kiro checks against known anti-patterns (concurrency, locks, cleanup)
4. If issues found: Kiro fixes directly or re-prompts the model
5. If new recurring pattern found: Kiro adds it to `anti-patterns.md`
6. Clean code presented to user

### Git Flow

```
local-dev ──[subagent writes]──[Kiro reviews]──[commit]──[push to Gitea]
                                                              │
main ─────────────────────────────[merge after approval]──────┘
```

## Model Selection

```
Task arrives
    │
    ├─ Contains prose keywords? ──────────→ qwen3:8b
    │  (readme, docs, tutorial, creative)
    │
    ├─ Contains complex keywords? ────────→ qwen3-coder:30b-a3b
    │  (auth, architecture, database, etc)
    │
    ├─ Short task (<100 chars)? ──────────→ qwen2.5-coder:7b
    │
    └─ Long task, no keywords ────────────→ qwen3-coder:30b-a3b
```

Fallback: if selected model fails (404, timeout), automatically tries next in chain.

## Skill System

Skills are markdown files with YAML frontmatter containing tags:

```yaml
---
name: Security
tags: [code, security]
description: Input validation, auth, secrets management.
---
```

The script selects skills by matching `--tags` against frontmatter tags. Skills tagged `always` are included in every call.

### Current Tags

| Tag | Meaning |
|---|---|
| `always` | Every call (software-engineering, anti-patterns) |
| `code` | Any code generation |
| `api` | API/endpoint work |
| `test` | Writing tests |
| `security` | Auth, validation, secrets |
| `review` | Code review |
| `refactor` | Restructuring |
| `optimization` | Performance |
| `docs` | Documentation |
| `git` | Version control |
| `release` | Versioning, changelogs |
| `new-project` | Scaffolding |
| `meta` | About the skill system |

## Self-Improvement Loop

```
Subagent generates → Kiro reviews → finds new bug pattern
    │                                       │
    │                                       ▼
    │                        Adds to anti-patterns.md
    │                        (tagged [always])
    │                                       │
    ▼                                       ▼
Next generation includes the new anti-pattern in its prompt
    → Model is told NOT to make that mistake
        → Pattern stops appearing
```

## File Structure

```
.kiro/
├── agents/
│   └── local-coder.md          # Subagent identity
├── hooks/
│   ├── review-after-generate    # Triggers review on new .py files
│   ├── review-local-diff        # Manual: review main..local-dev
│   └── sync-to-gitea            # Manual: push local-dev
├── scripts/
│   ├── local_coder.py           # Main orchestrator
│   ├── sync-gitea.bat           # Windows push helper
│   └── sync-gitea.sh            # Linux/Mac push helper
├── skills/                      # 15 skills (code standards)
│   ├── anti-patterns.md         # [always] — what NOT to do
│   ├── software-engineering.md  # [always] — how to write code
│   ├── api-design.md            # [code, api]
│   ├── security.md              # [code, security]
│   └── ...
└── steering/                    # Kiro behavior
    ├── codesearch.md            # Use CLI, not file reading
    ├── gitea-quirks.md          # Push twice
    ├── local-coder-integration.md  # When/how to delegate
    ├── memories.md              # Lessons learned
    ├── reviewer-persona.md      # Review focus areas
    ├── skills.md                # Skill activation protocol
    └── verification-and-honesty.md  # Don't guess, verify
```
