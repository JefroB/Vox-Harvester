---
inclusion: always
---

# CodeSearch — Pre-indexed search and code intelligence

Run `codesearch context` FIRST to see all commands and the token-efficient workflow.

## Critical rules

1. NEVER read whole files. NEVER loop through files reading them one by one.
2. NEVER use `cat`, `readFile`, shell loops, or equivalent to read source files when codesearch is available.
3. NEVER iterate over a list of files calling `get-file-content` on each one — this is the same as reading whole files and defeats the purpose of codesearch.
4. ALWAYS use batch/extraction commands that process multiple files in one call.
5. ALWAYS prefer codesearch tools over generic file reading for discovery and code inspection.

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

## Recovery rules (when a command fails or returns empty)

1. If `module-summary` fails, try `get-symbol-code <ClassName>` instead — never fall back to readFile/readMultipleFiles.
2. If `get-symbol-code` fails, try `search-content` with a more specific query to find the exact lines you need.
3. NEVER fall back to readFile, readMultipleFiles, or cat. If codesearch can't find it, tell the user and ask for guidance.
4. The fallback chain is: module-summary → get-symbol-code → search-content → ASK THE USER. File reading is not in this chain.

## `--path` usage

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

❌ Looping through files with `get-file-content`:
```
for f in "file1.js" "file2.js" "file3.js"; do
  codesearch get-file-content "$f" --start-line 1 --end-line 80
done
```
This is just reading whole files with extra steps. Use a batch command instead.

✅ Correct approach for test extraction:
```
codesearch extract-test-cases "parentalControls" --output results.md --path .
```
One command, all matching files processed, structured output.

❌ Reading a file then manually searching through it:
```
codesearch get-file-content src/big_file.py --start-line 1 --end-line 500
```

✅ Correct approach — search first, then read only what you need:
```
codesearch search-content "validate_input"
codesearch get-symbol-code validate_input
```

## Command syntax reminders

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

## Dev conventions

- Run tests: `.venv/bin/python -m pytest .subagentcoder/tests/ --no-header -q`
