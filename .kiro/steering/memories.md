---
inclusion: always
---

# Memories — Lessons Learned

Accumulated corrections, gotchas, and patterns to avoid. These are things that went wrong in past sessions and should not be repeated.

## CodeSearch CLI

- `--filter-path` does NOT exist. Use `--path` to specify the project root. There is no way to scope results to a subdirectory via CLI flag — search results already include file paths.
- `module-summary` requires the file to be indexed first. If it returns "Module not found", run `codesearch reindex-files <file>` first.
- `codesearch doctor` shows "Stale files" if files changed since last index — use this to verify the watcher is working.
- Content search query is a positional arg, not a flag: `codesearch search-content "query"` ✅ not `codesearch search-content --query "query"` ❌

## Ollama / Local Models

- Both qwen2.5-coder and qwen3-coder consistently put `time.sleep()` or `await` calls inside lock blocks. Always check for this after generation.
- The qwen3-coder model loads at 53% CPU / 47% GPU split on this machine (12GB RTX 5070). This is expected — model is 22GB total.
- First call after model load is slow (cold start). Subsequent calls are faster.
- `ollama ps` shows current model state. `ollama stop <model>` unloads it.
- The prose model (`qwen3:8b`) hallucinates project details. NEVER use it for technical docs that reference actual code, structure, or commands. Use it only for creative/marketing/user-facing text where factual accuracy about the codebase doesn't matter.
- `qwen3:8b` runs at ~100 tok/s on GPU — fastest of the three.

## Git / Gitea

- First push to Gitea always fails with auth error. Second push succeeds. Don't ask about credentials — just retry.
- Remote branch is `main` (not `master`).

## Windows / Shell

- PowerShell does not support `&` as command separator. Use `;` instead.
- `timeout /t N /nobreak >nul` doesn't work with `&`. Use `Start-Sleep -Seconds N` in PowerShell.
- stderr output in PowerShell triggers exit code 1 even when the command succeeded. Check actual output, not just exit code.

## Hook System

- `postToolUse` with `toolTypes: ["shell"]` fires on EVERY shell command — too noisy for conditional logic.
- `toolTypes` regex matches tool *names* (e.g., `execute_pwsh`), NOT command content. Can't filter by what's inside the command.
- `fileCreated` with path patterns is better for detecting generated output.

## Patterns That Don't Work (Anti-Memories)

- ❌ Trying to get per-process GPU memory on Windows WDDM — `nvidia-smi` always shows N/A.
- ❌ Assuming `ollama stop` + reload will change CPU/GPU split — it's determined by total model size vs available VRAM at load time.
- ❌ Using `--version` with codesearch — flag doesn't exist.
