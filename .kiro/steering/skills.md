---
inclusion: always
---

# Skill Activation Protocol

## Rule

At the start of every task, you MUST:

1. List the contents of `.kiro/skills/` to see all available skills.
2. For each skill file found, evaluate whether it is relevant to the current task based on the file name and context of the user's request.
3. Activate every skill that is relevant. When in doubt, activate it — false positives are cheaper than missing context.
4. Do NOT wait for the user to name a skill explicitly. Infer relevance from the task.

## Activation Criteria

A skill is relevant if the task involves ANY of the following:

| Skill file | Activate when the task involves... |
|---|---|
| `software-engineering.md` | Writing, reviewing, or designing code of any kind |
| `code-comments.md` | Writing or reviewing code (docstrings, inline comments, module headers) |
| `docs-folder.md` | Completing a spec, changing architecture/usage, writing project docs in `docs/` |
| `documentation-standards.md` | General documentation reference (legacy — prefer the two above for specifics) |
| `changelog.md` | Updating changelogs, versioning, release notes |
| `gitea.md` | Pushing, pulling, branching, PRs, commits, or any interaction with the local Gitea server |
| `testing-strategy.md` | Writing tests, choosing what to test, test structure, mocking, coverage |
| `security.md` | Input validation, auth, secrets, injection prevention, dependency auditing |
| `code-review.md` | Reviewing diffs, approving merges, identifying logic/security issues |
| `project-scaffolding.md` | Starting new projects, folder structure, config setup, entry points |
| `error-handling.md` | Error types, propagation, logging, user-facing messages, fail-fast patterns |
| `api-design.md` | REST/GraphQL design, endpoints, status codes, response shapes, pagination |
| `performance.md` | Profiling, caching, async patterns, algorithmic optimization, memory |
| `refactoring.md` | Restructuring code, extracting functions, reducing coupling, code smells |
| `skill-authoring.md` | Creating new skills, tagging system, frontmatter format |
| `local-model-review.md` | Reviewing output from local Ollama models, known weaknesses checklist |

This table is a starting point. New skills may be added at any time. Always scan the folder — do not rely on a hardcoded list.

## Multiple Skills

Most tasks will require multiple skills simultaneously. For example:
- Generating code with local-coder → activate `software-engineering`, `code-comments`, `gitea.md`
- Reviewing a diff → activate `code-review`, `security`, `software-engineering`
- Writing project docs → activate `docs-folder`, `software-engineering`
- Completing a spec → activate `code-comments`, `docs-folder`, `software-engineering`
- Starting a new project → activate `project-scaffolding`, `software-engineering`, `gitea`, `docs-folder`
- Building an API → activate `api-design`, `software-engineering`, `security`, `error-handling`, `code-comments`
- Writing tests → activate `testing-strategy`, `software-engineering`
- Optimizing slow code → activate `performance`, `refactoring`, `software-engineering`
- Fixing a bug → activate `software-engineering`, `error-handling`, `testing-strategy`

## New Skills

The skills folder will grow over time. Every time you scan it, you may find new files you haven't seen before. Read them and apply the same relevance logic. If a new skill doesn't have a row in the table above, infer activation criteria from the skill's content.

## Context-Based Activation (Not Just User Words)

Do NOT rely solely on keywords in the user's message. Also infer skill relevance from:

1. **Open/active editor files** — if the user has a source file open, activate `software-engineering`.
2. **Spec content** — if executing a spec task, read the spec's requirements/design/tasks and activate skills matching the domain.
3. **File paths in context** — if the task touches `.kiro/` config, activate `gitea-workflow` or `local-coder-workflow` as appropriate.
4. **Task descriptions** — when running spec tasks, the task text itself contains signals.
5. **Transitive relevance** — if a skill is activated and it references concepts covered by another skill, activate that too.

**Rule of thumb:** If you'd need to consult a skill's knowledge to do the task well, activate it. Don't wait for the user to spell it out.

## Execution

After activating relevant skills, proceed with the task. Do not announce which skills you activated unless the user asks.
