# Workflow Guide

## Daily Usage

### Starting a Session

1. Make sure Ollama is running (`ollama list` to verify)
2. Open your project in Kiro
3. The codesearch watcher should auto-start, or run: `codesearch watch --path .`

### Generating Code

Just ask Kiro to build something. Examples:

- "Generate a REST API handler for user registration"
- "Write unit tests for the auth module"
- "Create a config parser that reads YAML and validates against a schema"

Kiro will:
1. Determine complexity → select the right model
2. Pick relevant skills/tags → inject into the prompt
3. Call the local model → get code back
4. Review the output → fix any issues
5. Present clean code to you

### Forcing a Specific Approach

If auto-routing picks wrong:

- "Use the fast model for this" → Kiro will use `--complexity simple`
- "This needs the heavy model" → `--complexity complex`
- "Write this as prose, not code" → `--complexity prose`

### Reviewing Changes

Click **Review Local Dev Diff** in the Agent Hooks panel, or say:
"Review the diff between main and local-dev"

### Pushing to Gitea

Click **Sync to Gitea** in the Agent Hooks panel, or say:
"Push local-dev to Gitea"

### Merging to Main

Ask Kiro: "Merge local-dev into main"

Kiro will only do this after reviewing — never merges unreviewed code.

## The Generate-Review-Fix Loop

Every piece of generated code goes through this cycle:

```
Generate → Index → Review → Fix → (loop if needed) → Present
```

This is enforced by:
- Steering file: `local-coder-integration.md`
- Hook: `review-after-generate`
- Skill: `local-model-review.md` (known weaknesses checklist)

You don't need to ask for review — it happens automatically.

## Adding Skills for a New Project

When you start a new project on top of this template:

1. Identify what domain you're working in (web app? CLI tool? game?)
2. Create domain-specific skills in `.kiro/skills/`:
   ```yaml
   ---
   name: Django Patterns
   tags: [code, web]
   description: Django-specific conventions, models, views, URLs.
   ---
   ```
3. The subagent will automatically pick them up via tags

## Token Budget

Track how many cloud tokens you've avoided:

```bash
# Local model savings (code generation offloaded to GPU)
python .kiro/scripts/local_coder.py --stats

# CodeSearch savings (reading code without consuming full files)
codesearch token-savings
```

The `--stats` output shows:
- Total local model calls and tokens generated locally
- Breakdown by model (which model saved the most)
- CodeSearch savings alongside
- Combined total of all cloud tokens avoided

Both tools write to the same SQLite database (`.codesearch/index.db`), so the numbers are always in sync.

## Troubleshooting

### "Model not found" error
The requested model isn't pulled. Run: `ollama pull <model-name>`
The script will auto-fallback to another model, but pull the right one for best results.

### Slow generation
Check `ollama ps` — if the model shows CPU/GPU split, other apps are using VRAM.
Close browsers, Discord, etc. to free GPU memory.

### CodeSearch "Module not found"
The file isn't indexed yet. Run: `codesearch reindex-files <file>`
Or wait 2s for the watcher to pick it up.

### Gitea push fails
First push always fails (server quirk). It retries automatically.
If both fail, check your network connection to 192.168.1.25.
