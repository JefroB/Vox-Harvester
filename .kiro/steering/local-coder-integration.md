---
inclusion: always
---

# Local Coder Integration

## When to Use the Local Model

When the user asks you to **generate**, **implement**, or **write** code — especially bulk implementations, boilerplate, CRUD operations, parsers, or tests — consider delegating to the local Ollama model instead of generating it yourself. This saves cloud tokens.

Indicators to use local generation:
- User says "generate", "implement", "write", "scaffold", "build"
- The task is straightforward implementation (not complex architecture)
- The task involves repetitive patterns or boilerplate
- The user explicitly asks to use the local coder

Do NOT delegate when:
- The task requires complex reasoning about the project's architecture
- You need to read and understand multiple existing files to produce correct code
- The task is a review, analysis, or planning exercise
- The task is small (a one-liner fix, a rename, etc.)

## How to Call the Local Model

Run the script from the workspace root:

```
python .kiro/scripts/local_coder.py --task "<detailed task description>" --skills <skill1> <skill2> ... --output <target-file>
```

### Task ID Tracking

When calling from a spec-task-execution context, **always pass `--task-id`** so token savings are linked to the correct task:

```
python .kiro/scripts/local_coder.py --task "..." --task-id "1.2" --tags code --output src/module.py
```

The `--task-id` value should be the spec task ID (e.g., "1.1", "2.3"). This enables per-task token savings tracking in the result database. If omitted, a random UUID is used and the result can't be correlated to a specific task.

## CRITICAL: Skill Selection is YOUR Responsibility

The local model has NO ability to discover or activate skills. It only receives what you inject. YOU must select the right skills for every call.

### Primary Method: Tags (Preferred)

Use `--tags` to select skills by category. The script reads frontmatter tags from each skill file and includes all matching ones. Skills tagged `always` are auto-included regardless.

```bash
python .kiro/scripts/local_coder.py --task "..." --tags code api security
```

### Tag Reference

| Tag | Selects skills related to... |
|---|---|
| `code` | General coding standards, docs, errors, security, testing, performance, refactoring |
| `api` | API/endpoint design |
| `test` | Testing patterns |
| `security` | Auth, validation, secrets |
| `refactor` | Code restructuring |
| `optimization` | Performance improvement |
| `docs` | Documentation |
| `git` | Version control, commits |
| `release` | Versioning, changelogs |
| `new-project` | Project scaffolding |
| `review` | Code review |

### Selection Rules

1. `software-engineering` is ALWAYS included (tagged `always`).
2. Match tags to the task type:

| Task type | Use these tags |
|---|---|
| Writing a feature | `--tags code` |
| Building an API | `--tags code api security` |
| Writing tests | `--tags code test` |
| Refactoring | `--tags code refactor` |
| New project setup | `--tags code new-project` |
| Everything (complex task) | `--all-skills` |

3. When in doubt, use `--tags code` — it covers the core standards.
4. For critical features (auth, payments), always add `security`.

### Example Calls

```bash
# Simple function — tags select relevant skills automatically
python .kiro/scripts/local_coder.py --task "Write a Python function that validates email addresses" --tags code --output src/validators.py

# API handler — code + api + security tags pull in 8+ relevant skills
python .kiro/scripts/local_coder.py --task "Create a REST endpoint for user registration" --tags code api security --output src/routes/register.py

# Explicit skill names still work (override tag system)
python .kiro/scripts/local_coder.py --task "Add retry logic" --skills error-handling performance --output src/http_client.py

# Mix tags + explicit skills + context files
python .kiro/scripts/local_coder.py --task "Add auth middleware" --tags code security --context src/server.py --output src/middleware/auth.py

# When in doubt, send everything
python .kiro/scripts/local_coder.py --task "Build the complete auth module" --all-skills --output src/auth/module.py

# Minimal prompt for fully-specified tasks (JSON, config files) — reduces garbage
python .kiro/scripts/local_coder.py --task "Create config.json with these exact contents: ..." --minimal-prompt --complexity simple --output config.json

# Property tests — always include a passing test as context
python .kiro/scripts/local_coder.py --task "Write property tests for validateX" --tags code test --complexity complex --context src/test/existing-passing.test.ts src/core/target.ts --output src/test/target.property.test.ts
```

## Providing Context

When the task references or extends existing code, use `--context` to include those files:
```
--context src/models.py src/database.py
```
This injects the file contents into the prompt so the subagent can see the existing code. Use this when:
- The new code needs to match existing interfaces
- You're extending/modifying an existing module
- The task says "add X to this file"

## Output Handling

- The script auto-strips markdown fences by default (extracts raw code)
- Use `--raw` flag if you need the full response with explanations
- Use `--dry-run` to preview the prompt without calling Ollama (useful for debugging)
- Review the output for correctness before writing it to the project

## After Generation

**MANDATORY: Every generated output MUST be reviewed before being presented to the user or written to the project.**

### The Generate-Review-Fix Loop

1. **Generate** — Call the local model with the task
2. **Index** — Run `codesearch reindex-files <generated-file>` so codesearch can see it
3. **Review** — Use codesearch to inspect the output:
   - `codesearch module-summary <file>` for structure overview
   - `codesearch get-symbol-code <ClassName>` to inspect specific implementations
   - `codesearch search-content "time.sleep" --filter-path <file>` to find known anti-patterns
   - For fast-check tests: run `from local_coder.fast_check_linter import lint_fast_check` to detect anti-patterns
   - Check for:
     - Logic bugs (especially concurrency, off-by-one, unhandled edge cases)
     - Missing error handling or input validation
     - Thread safety (sleeping inside locks, race conditions)
     - Incomplete implementations (TODOs, stubs, placeholders)
     - Missing requirements from the original task
     - Math.random() inside fc.property (always wrong)
     - Missing `export` keywords on public functions
     - Hardcoded field counts in validators (use REQUIRED_FIELDS.length instead)
4. **Fix** — If issues are found:
   - Write specific fix instructions as a new task
   - Call the local model again with `--context <the-generated-file>` and the fix instructions
   - OR fix the issues yourself directly (faster for small fixes)
5. **Re-review** — Check the fixed output. Loop until clean.
6. **Write** — Only write to the project once the code passes review.

### When to fix locally (Kiro) vs re-prompt Qwen:
- **Small fixes** (missing import, typo, rename) → fix yourself, don't re-prompt
- **Structural issues** (wrong algorithm, missing class, bad API) → re-prompt Qwen with specific instructions
- **Concurrency/safety bugs** → fix yourself (Qwen consistently misses these)

### NEVER skip review. Even for simple tasks, do a quick scan for:
- Undefined variables
- Missing imports
- Functions that don't return what they claim
- Lock/resource leaks

## Model Details

Three models are available with smart routing:

| Model | Complexity | Speed | Use for |
|---|---|---|---|
| `qwen2.5-coder:7b` | simple | ~50+ tok/s (100% GPU) | Simple functions, boilerplate, data/configs, single-file tasks |
| `qwen3-coder:30b-a3b-q4_K_M` | complex | ~14-25 tok/s (CPU/GPU split) | Complex logic, multi-file, architecture, auth/security, technical docs |
| `qwen3:8b` | prose | ~100 tok/s (100% GPU) | Creative writing, user-facing copy, marketing, translations |

### Routing

The script auto-routes by default (`--complexity auto`):
- Tasks containing prose keywords (creative writing, marketing copy, blog post, translate, i18n, etc.) → prose model
- Tasks containing code complexity keywords (architecture, auth, security, database, module, etc.) → heavy model  
- Short tasks (<100 chars) without any keywords → fast model
- Override with `--complexity simple`, `--complexity complex`, or `--complexity prose`

### IMPORTANT: Prose Model vs Technical Docs

The prose model (`qwen3:8b`) is a general language model — it writes fluently but **hallucinates facts** about the codebase. NEVER use it for:
- READMEs that reference actual project structure
- Architecture docs
- API documentation
- Tutorials that include real code paths

For technical documentation, either write it yourself (Kiro) or use the heavy code model with `--context` pointing at the relevant source files.

### Configuration

- Endpoint: http://localhost:11434
- Context: 32768 tokens (configurable via `--ctx-size`)
- Temperature: 0.2 default (low creativity, high precision)
- Garbage retry: auto-bumps to 0.4 (low temp can cause degenerate loops)
- Timeout: auto-scaled based on prompt size (60s base + 3s per 100 tokens, capped at 600s)

## Fallback

If Ollama is unreachable or the model fails, inform the user and offer to generate the code directly (cloud-side). Don't silently fall back.

## Enforcement During Spec Task Execution

**When you are executing a spec task (dispatched by the orchestrator) and the task has a `[local-coder: ...]` annotation:**

This is NOT optional guidance. It is a hard constraint:

1. You MUST call `python .kiro/scripts/local_coder.py` with the flags from the annotation
2. You MUST NOT write implementation code, test code, or boilerplate yourself
3. You MUST NOT skip the call because you think you can do it faster or better
4. You MAY review and fix the output after generation
5. You MAY implement directly ONLY if local_coder.py exits with a non-zero code (Ollama down, timeout, garbage escalation) — and you must log the fallback reason

**Why this matters:** Every cloud-implemented task that should have been delegated costs the user real money in cloud tokens and produces no data in the result database for tracking local model performance.

**The orchestrator will verify:** If a `[local-coder: ...]` task completes without any `python .kiro/scripts/local_coder.py` call in the execution history, it will be flagged as a delegation failure.

## Debugging

- Use `--dry-run` to see exactly what prompt would be sent
- Use `--list-skills` to see available skills
- Check stderr for `[WARN]` messages about missing skills or context budget
- The script reports token generation speed after each call

## Orchestrator Enforcement (When Dispatching to Subagents)

When the orchestrator dispatches a `[local-coder: ...]` annotated task to a subagent, the enforcement pipeline ensures compliance at three levels:

### Level 1: Prompt Injection (Option B — `execution_hook.inject_delegation_prompt`)

The dispatch pipeline calls `inject_delegation_prompt(description)` before sending the task to a subagent. This programmatically prepends the mandatory delegation block — no reliance on the orchestrator "remembering" to include it.

### Level 2: Post-Execution Audit (Option A — `dispatch.audit_wave_delegation`)

After a wave completes, the orchestrator calls `audit_wave_delegation(wave_results, task_registry)` to check each result for evidence of `local_coder.py` execution. Violations are:
- Logged to stderr with `[ERROR] dispatch: DELEGATION BYPASS detected`
- Returned as a list of violation dicts for re-queuing or escalation

### Level 3: Result Database Tracking (Option C — `delegation_method` field)

Every `TaskResult` record now includes a `delegation_method` field:
- `"local"` — `local_coder.py` was called
- `"cloud"` — implemented cloud-side (legitimate or not)
- `"escalated"` — local failed, escalated to cloud

Query delegation compliance stats:
```python
db.query_results({"delegation_method": "cloud"})  # Find all cloud-implemented tasks
db.compute_success_rate("delegation_method")       # Success rates by delegation method
```

### Cost Justification

Each bypassed local-coder task wastes 4K–16K cloud tokens on work that costs zero locally. Over a 10-task spec, that's 40K–160K wasted tokens. These enforcement mechanisms make bypass visible and auditable.
