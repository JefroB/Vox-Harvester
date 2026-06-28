---
name: Skill Authoring
tags: [meta]
description: How to create new skill files with proper structure, frontmatter, and tagging so the subagent activates them correctly.
---

# Skill Authoring

## Purpose

This skill defines how to create new skill files that work correctly in both Kiro (cloud) and the local Ollama subagent. Proper tagging ensures skills are automatically selected when relevant.

## File Location

All skills live in `.kiro/skills/` as markdown files.

## Required Structure

Every skill file MUST have this structure:

```markdown
---
name: Human Readable Name
tags: [tag1, tag2]
description: One-line description of what this skill covers.
---

# Skill Title

## Core Principle

One sentence that captures the philosophy.

## Rules / Patterns / Content

The actual skill content...
```

## Frontmatter Schema

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Human-readable name for display |
| `tags` | Yes | Array of tags for automatic selection |
| `description` | Yes | One-line summary — shown in listings |

## Tag System

Tags determine when a skill is automatically injected into the local subagent's prompt.

### Reserved Tags

| Tag | Meaning | Auto-selected when... |
|---|---|---|
| `always` | Injected into EVERY call | Always — no conditions needed |
| `code` | General code writing standards | Any code generation task |
| `api` | API design patterns | Building endpoints, APIs, services |
| `test` | Testing patterns | Writing tests of any kind |
| `security` | Security standards | Auth, validation, secrets handling |
| `review` | Code review guidance | Reviewing diffs or PRs |
| `refactor` | Refactoring patterns | Restructuring existing code |
| `optimization` | Performance patterns | Speed/memory optimization work |
| `docs` | Documentation rules | Writing docs, comments, READMEs |
| `git` | Version control rules | Commits, branches, pushes |
| `release` | Release/versioning rules | Bumping versions, changelogs |
| `new-project` | Scaffolding guidance | Starting a new project from scratch |
| `meta` | About the skill system itself | Only relevant when authoring skills |

### Adding New Tags

When existing tags don't fit, create new ones following these rules:
- Use lowercase, single words (or hyphenated for compound concepts)
- Be specific enough to be useful, generic enough to be reusable
- Document the tag's meaning with a comment in the skill's description
- Prefer existing tags over creating new ones when possible

### Tagging Guidelines

1. Use 1-3 tags per skill. More than 3 suggests the skill is too broad — split it.
2. Use `always` sparingly — only for truly universal standards (currently just `software-engineering`).
3. Use `code` for skills that apply to ANY code generation regardless of domain.
4. Use domain-specific tags (e.g., `api`, `security`, `test`) for focused skills.
5. A skill can combine generic + specific: `[code, security]` means "relevant to all code, especially security."

## Writing Effective Skills

### Do:
- Write rules as direct imperatives ("Validate all input", not "Input should be validated")
- Include concrete examples (code snippets, good/bad comparisons)
- Keep sections focused — one concept per section
- Include anti-patterns (what NOT to do) with ❌ markers
- Keep total length under 200 lines — beyond that, split into multiple skills

### Don't:
- Write essays or theory — skills are reference guides, not textbooks
- Include language-specific syntax unless the skill IS language-specific
- Repeat content already in another skill — reference it instead
- Add vague advice ("write good code") — be specific and actionable
- Include Kiro-specific workflow instructions (those go in steering files)

## Skill vs Steering

| Content type | Goes in... |
|---|---|
| Coding standards and patterns | `.kiro/skills/` |
| Workflow instructions for Kiro | `.kiro/steering/` |
| When/how to use tools or scripts | `.kiro/steering/` |
| Universal code quality rules | `.kiro/skills/` |
| Project-specific conventions | `.kiro/skills/` (tagged for the domain) |

The key distinction: **Skills are consumed by BOTH Kiro and the subagent.** Steering is Kiro-only.

## After Creating a New Skill

1. Verify the frontmatter parses correctly: `python .kiro/scripts/local_coder.py --list-skills`
2. Verify tag selection works: `python .kiro/scripts/local_coder.py --task "test" --tags <your-tag> --dry-run`
3. Update `.kiro/steering/skills.md` activation table with a new row for the skill
4. The subagent will automatically pick it up on the next tagged call — no restart needed.
