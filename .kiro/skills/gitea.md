---
name: Gitea & Versioning
tags: [git, release]
description: Gitea server usage, commit rules, branching strategy, version bumps.
---

# Gitea & Versioning

## Version Numbers

- The project uses Semantic Versioning (semver): MAJOR.MINOR.PATCH
- The canonical version lives in the project's primary config file (e.g., `package.json`).
- PATCH: bug fixes, minor QoL changes, no new features
- MINOR: new user-facing features, non-breaking behavioral changes
- MAJOR: breaking changes to behavior or data formats

## When to Bump

- Version is bumped EVERY TIME the user says to commit and push. No exceptions.
- All changes between commits belong to the same version bump.
- Never bump version speculatively or on individual file saves — ONLY on commit.
- When bumping, update:
  1. The project's version config file
  2. `docs/CHANGELOG.md` — move `[Unreleased]` to `[x.y.z] - YYYY-MM-DD`

**CRITICAL**: If the user says "commit and push" and you don't bump the version, that is a mistake. Every commit to Gitea gets a new version number.

## Commit Rules

- Only commit when the user explicitly asks.
- Use conventional commit messages: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`
- Stage specific files — never use `git add .`
- Push to the current working branch (check with `git branch --show-current`), not main/master, unless explicitly told otherwise.
- Use `git push -u origin <branch>` for first push of a new branch.

## Commit Message Format

```
type: short description (≤70 chars)

- bullet point details if needed
- reference changelog entries
```

## Branch Strategy

- `main`: Production-ready, cloud-verified code.
- `local-dev`: Workspace for the local-coder subagent (Ollama).
- Feature branches: for isolated work before merging to local-dev or main.
- The user manages merges to main — never merge or rebase without being told.
- Branch naming: descriptive kebab-case (e.g., `fix-auth-flow`, `feat-parser`)

## Gitea Server

- URL: http://192.168.1.25:3000
- User: Jefro
- Repo: SubAgent-Coder
- Protocol: HTTP
- Quirk: First push often fails with an auth error. Always retry once before reporting failure.

## Pre-Commit Checklist

Before committing, verify:
1. The project builds/lints without errors
2. `docs/CHANGELOG.md` is up to date with all changes in this version bump
3. Version is bumped appropriately
4. No temp/debug files are staged
