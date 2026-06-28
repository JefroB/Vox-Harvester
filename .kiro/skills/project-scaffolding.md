---
name: Project Scaffolding
tags: [new-project]
description: Folder layout, config files, entry points, how to start a new project.
---

# Project Scaffolding

## Core Principle

A good project structure makes the right thing easy and the wrong thing obvious. Structure should be predictable, minimal at first, and grow with the project.

## Universal Layout

Regardless of language or framework, most projects share this shape:

```
project-root/
├── src/              # Source code (or lib/, app/, pkg/)
├── tests/            # Test files (mirrors src/ structure)
├── docs/             # Project documentation
├── scripts/          # Build, deploy, utility scripts
├── .gitignore        # VCS exclusions
├── README.md         # Project overview, setup, usage
└── <config files>    # package.json, pyproject.toml, Cargo.toml, etc.
```

## Rules

### Start minimal
- Create only what's needed now. Don't pre-create folders "in case."
- A flat structure is fine for small projects. Nest when things get crowded (>7 files in a folder).

### Separation of concerns
- Keep source, tests, docs, and scripts separate
- Config files live at root
- Don't mix runtime code with build tooling

### Naming conventions
- Use lowercase with dashes or underscores for folders (match the ecosystem norm)
- Be descriptive: `auth/`, `api/`, `models/` over `stuff/`, `misc/`, `utils2/`
- `utils/` is acceptable for genuinely shared helpers — not as a dumping ground

### Entry points
- Every project needs a clear entry point (e.g., `main.py`, `index.ts`, `cmd/main.go`)
- README should explain how to run, build, and test within the first 10 lines

### Config files
- One source of truth for project metadata (package.json, pyproject.toml, etc.)
- Environment-specific config via `.env` files (never committed) or config/ folder
- Keep CI/CD config at root (`.github/`, `.gitlab-ci.yml`, `Makefile`)

## When Scaffolding a New Project

1. Identify the language/framework and follow its ecosystem conventions
2. Create the minimal structure: src/, one entry point, one config file, README, .gitignore
3. Set up version control immediately (git init, first commit)
4. Add a build/run command to README before writing any features
5. Add linting/formatting config early — it's painful to retrofit

## Anti-Patterns

- ❌ Deep nesting from day one (`src/core/modules/base/abstract/impl/`)
- ❌ Multiple "main" files with unclear which is the real entry point
- ❌ No README or a README that says "TODO"
- ❌ Source code mixed with docs, scripts, and config in one flat directory
- ❌ Generated/compiled output committed to version control (build/, dist/, __pycache__/)
