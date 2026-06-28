---
inclusion: always
---

# CodeSearch — Primary Code Intelligence Tool

CodeSearch is the FIRST tool for all code discovery, inspection, and understanding. Built-in tools (`read_file`, `read_files`, `read_code`, `grep_search`, `file_search`) are FALLBACK ONLY — used when codesearch fails or returns empty after a genuine attempt.

Run `codesearch context` FIRST to see all commands and the token-efficient workflow.

## Enforcement: The Codesearch-First Rule

**BEFORE using any built-in file tool on source code (.py, .ts, .tsx, .js, .jsx, .json in src/), you MUST:**

1. Have already tried the appropriate codesearch command for the task
2. Received an empty result, an error, or confirmed that codesearch cannot answer the question
3. Only THEN may you fall back to a built-in tool

**Violations of this rule:**
- Using `read_file` or `read_code` on a source file without a prior codesearch attempt in the same turn
- Using `grep_search` to search source code without first trying `codesearch search-content`
- Using `file_search` to find source files without first trying `codesearch search-files`
- Using `read_files` to bulk-read source without first trying `module-summary` or `search-content`

**Exceptions (built-in tools allowed directly):**
- `.kiro/` files (specs, steering, config, hooks, scripts)
- `docs/` folder files
- `package.json`, `pyproject.toml`, `tsconfig.json`, and root config files
- Files you are ABOUT TO EDIT (you need the exact current content for `str_replace`)
- Files explicitly provided by the user in context (#File references)

## Decision Matrix

| I need to... | Use this FIRST | Fallback if it fails |
|---|---|---|
| Find where something is defined | `codesearch get-definition <NAME>` | `grep_search` |
| Read a function's implementation | `codesearch get-symbol-code <NAME>` | `read_file` with line range |
| Understand a module's structure | `codesearch module-summary <FILE>` | `read_code` |
| Search for a pattern across files | `codesearch search-content "query"` | `grep_search` |
| Find files by name | `codesearch search-files <PATTERN>` | `file_search` |
| Understand call relationships | `codesearch get-callers/get-callees <NAME>` | `grep_search` for references |
| Get project overview | `codesearch project-overview` or `repo-map` | `list_directory` with depth |
| Find architecture relationships | `codesearch graph explain <NODE>` | N/A (no equivalent) |
| Extract test patterns | `codesearch extract-test-cases <PAT>` | `grep_search` + `read_file` |
| Edit a file (need current content) | `read_file` directly (exception) | — |

## Critical Rules

1. NEVER read whole source files without a prior codesearch attempt.
2. NEVER loop through files reading them one by one — use batch codesearch commands.
3. NEVER use `cat`, shell loops, or equivalent for source file reading.
4. ALWAYS prefer codesearch for discovery and inspection over generic file reading.
5. If codesearch is down or the index is stale, say so explicitly before falling back to built-in tools.

## Workflow (follow this order)

1. **Discover** — find what you need:
   - `codesearch search-content "query"` — grep-like content search across all files
   - `codesearch search <QUERY>` — symbol search by name
   - `codesearch search-files <PATTERN>` — find files by name pattern
   - `codesearch project-overview` — high-level stats and top modules
   - `codesearch repo-map` — structural overview of the codebase

2. **Inspect** — understand structure without reading full files:
   - `codesearch module-summary <FILE>` — symbols, imports, dependents (no source code)
   - `codesearch get-symbol-code <NAME>` — just the implementation of one symbol
   - `codesearch get-definition <NAME>` — location and signature only
   - `codesearch get-callers <NAME>` / `codesearch get-callees <NAME>` — call graph

3. **Knowledge Graph** — understand relationships and architecture:
   - `codesearch graph path <SOURCE> <TARGET>` — shortest path between two symbols/files
   - `codesearch graph explain <NODE>` — full summary of a node (community, centrality, callers, callees, docs, rationale)
   - `codesearch graph neighbours <NODE>` — direct neighbours with edge metadata
   - `codesearch graph god-nodes` — highest-centrality nodes in the codebase

4. **Extract** — pull structured data from multiple files at once:
   - `codesearch extract-test-cases <PATTERN> --output FILE` — extract test cases matching a pattern
   - `codesearch export-tests <PATTERN> --output FILE` — export tests to markdown/json/csv
   - `codesearch count-tests --pattern <PAT>` — count test methods across files

5. **Read** — LAST RESORT, only for a specific section of ONE file:
   - `codesearch get-file-content <FILE> --start-line N --end-line M`
   - Always use `--start-line` and `--end-line`. Do NOT omit them.
   - If you need content from multiple files, you are doing it wrong. Go back to step 3 or use `search-content`.

## Fallback Chain (when codesearch fails)

```
codesearch command → retry with adjusted query → built-in tool → ASK THE USER
```

Specific fallback paths:
1. `module-summary` fails → try `get-symbol-code <ClassName>` → if that fails, `read_code` on the file
2. `get-symbol-code` fails → try `search-content` with the symbol name → if that fails, `grep_search`
3. `search-content` returns empty → widen the query OR use `grep_search`
4. `search-files` returns empty → use `file_search`
5. Index is stale/missing → state this explicitly, then use built-in tools

**Key rule:** When falling back, state WHY codesearch didn't work (e.g., "codesearch returned empty for X, falling back to grep_search").

## `--path` Usage

`--path` is the PROJECT ROOT where `codesearch index` was run (where `.codesearch/index.db` lives). It is NOT a subfolder or package path. If you're already `cd`'d into the project root, you can omit it.

There is NO `--filter-path` option. To scope results to a subdirectory, grep the output or use more specific search terms.

✅ CORRECT — run from project root, omit `--path`:
```
codesearch search-content "auth"
```

✅ CORRECT — specify project root explicitly:
```
codesearch search-content "auth" --path /path/to/project
```

❌ WRONG — passing a subfolder as `--path`:
```
codesearch search-content "auth" --path "src/packages/adobe-authentication"
```

## Anti-patterns (DO NOT DO THESE)

❌ Using `read_file` on a source file as your first action:
```
# WRONG — no codesearch attempt first
read_file("src/audio_validation/preprocessor.py")
```

✅ Correct approach:
```
codesearch module-summary src/audio_validation/preprocessor.py
# Then if needed:
codesearch get-symbol-code PreprocessorClass
```

❌ Using `grep_search` as your first search tool:
```
# WRONG — codesearch search-content should come first
grep_search(query="validate_input", includePattern="**/*.py")
```

✅ Correct approach:
```
codesearch search-content "validate_input"
# Only if empty: grep_search as fallback
```

❌ Looping through files with `get-file-content` or `read_files`:
```
# WRONG — batch reading defeats codesearch
read_files(paths=["file1.py", "file2.py", "file3.py"])
```

✅ Correct approach:
```
codesearch extract-test-cases "parentalControls" --output results.md
# One command, all matching files processed, structured output
```

❌ Reading a file then manually searching through it:
```
codesearch get-file-content src/big_file.py --start-line 1 --end-line 500
```

✅ Correct approach — search first, then read only what you need:
```
codesearch search-content "validate_input"
codesearch get-symbol-code validate_input
```

## Command Syntax Reminders

```
codesearch extract-test-cases <PATTERN> --output FILE [--path PATH] [--exclude PAT] [--filter-path PREFIX] [--test-type TYPE] [--format markdown|json]
codesearch count-tests [--pattern PAT] [--exclude PAT] [--path PATH]
codesearch export-tests <PATTERN> --output FILE [--format markdown|json|csv]
codesearch get-file-content <FILE> [--start-line N] [--end-line M] [--path PATH]
codesearch search-content <QUERY> [--limit N] [--path PATH]
codesearch get-symbol-code <NAME> [--path PATH]
codesearch module-summary <MODULE_PATH> [--path PATH]
codesearch graph path <SOURCE> <TARGET> [--max-depth N] [--min-confidence F] [--format text|json]
codesearch graph explain <NODE> [--min-confidence F] [--format text|json]
codesearch graph neighbours <NODE> [--depth N] [--provenance EXTRACTED|INFERRED|AMBIGUOUS] [--min-confidence F]
```

PATTERN is always a positional argument (first arg), not an option.
`--path` is always the project root directory, never a file path.

## Dev Conventions

- Run tests: `.venv/bin/python -m pytest .subagentcoder/tests/ --no-header -q`
