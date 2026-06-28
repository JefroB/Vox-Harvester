---
name: Changelog Management
tags: [git, release]
description: Changelog format, version bumps, when and how to update CHANGELOG.md.
---

# Changelog Management

## File Location

`docs/CHANGELOG.md`

## Format

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/):

```markdown
## [Unreleased]

### Added
- New features

### Changed
- Changes to existing functionality

### Fixed
- Bug fixes

### Removed
- Removed features

### Deprecated
- Soon-to-be removed features
```

## Rules

### When to Update

- After EVERY code change that affects user-visible behavior, update `docs/CHANGELOG.md` immediately.
- Group changes under `[Unreleased]` until the user asks to commit/push.
- When committing, move `[Unreleased]` entries under a versioned heading: `## [x.y.z] - YYYY-MM-DD`

### Entry Style

- One line per change, starting with a verb (past tense): "Fixed", "Added", "Changed", "Removed"
- Be specific and user-facing: describe WHAT changed from the user's perspective, not implementation details
- Bad: "Refactored reducer to use spread operator"
- Good: "Fixed config not reloading after saving changes"
- Include the root cause in parentheses when it adds clarity: "Fixed build failing on Windows (path separator mismatch)"

### Categories

- **Added**: New features, new capabilities
- **Changed**: Behavioral changes, QoL improvements, defaults changed
- **Fixed**: Bug fixes (something was broken, now it works)
- **Removed**: Features or options taken away
- **Deprecated**: Still works but will be removed

### On Commit

When the user says to commit:
1. Pick the appropriate version bump (patch/minor/major) based on the entries
2. Replace `[Unreleased]` with `[x.y.z] - YYYY-MM-DD`
3. Add a fresh empty `[Unreleased]` section above it
4. Update version in the project's primary config file (e.g., `package.json`)

### Internal-Only Changes

Changes that are purely internal (refactors with no behavior change, test additions, dev tooling) go under a `### Internal` subsection. These don't influence the version bump decision but are good to track.
