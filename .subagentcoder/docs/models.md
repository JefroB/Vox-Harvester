# Models Reference

## Available Models

| Model | Size (disk) | VRAM Usage | Speed | Best For |
|---|---|---|---|---|
| `qwen2.5-coder:7b` | 4.7 GB | ~5 GB (100% GPU) | ~50+ tok/s | Simple code, boilerplate, configs, data |
| `qwen3-coder:30b-a3b-q4_K_M` | 18 GB | 22 GB (53% CPU / 47% GPU) | ~14-25 tok/s | Complex logic, architecture, security |
| `qwen3:8b` | 5.2 GB | ~5 GB (100% GPU) | ~50+ tok/s | Prose, docs, creative writing, i18n |

## Routing Logic

The `local_coder.py` script auto-selects based on task keywords:

### Prose Model (`qwen3:8b`)
Triggered by: readme, documentation, explain, tutorial, guide, user-facing, copy, creative, blog, article, changelog entry, commit message, translate, i18n, localization, marketing, announcement

### Heavy Model (`qwen3-coder:30b-a3b`)
Triggered by: architecture, design, multiple files, module, refactor, auth, security, database, migration, API, system, integration, service, middleware, pipeline, orchestrat, complex, multi-step, full implementation, entire, complete module

### Fast Model (`qwen2.5-coder:7b`)
Default for: short tasks (<100 chars), anything that doesn't match prose or complex keywords.

## Fallback Chain

If the selected model fails (not loaded, timeout, error):

| Primary | Falls back to |
|---|---|
| qwen3-coder:30b | qwen2.5-coder:7b |
| qwen2.5-coder:7b | qwen3-coder:30b |
| qwen3:8b | qwen2.5-coder:7b |
| Unknown model | qwen2.5-coder:7b |

## Hardware Notes (RTX 5070, 12GB VRAM)

- `qwen2.5-coder:7b` fits entirely in VRAM. Fastest inference.
- `qwen3:8b` fits entirely in VRAM. Same speed tier as the 7b coder.
- `qwen3-coder:30b-a3b` is a MoE model (30B total, 3.3B active per token). At Q4 quantization it's 18GB on disk, loads as 22GB with KV cache. Splits ~53% CPU / 47% GPU on this card. Still usable at 14-25 tok/s.
- Only one model can be hot at a time. Switching models takes 10-30s for cold load.

## Manual Override

```bash
# Force a specific model
python .kiro/scripts/local_coder.py --task "..." --model qwen2.5-coder:7b

# Force a complexity tier
python .kiro/scripts/local_coder.py --task "..." --complexity simple
python .kiro/scripts/local_coder.py --task "..." --complexity complex
python .kiro/scripts/local_coder.py --task "..." --complexity prose
```

## Adding New Models

1. Pull the model: `ollama pull <model-name>`
2. Update the environment variable or edit `local_coder.py` constants:
   - `FAST_MODEL`, `HEAVY_MODEL`, or `PROSE_MODEL`
3. Test: `python .kiro/scripts/local_coder.py --task "test" --model <new-model>`
4. Update this doc.

## Known Model Behaviors

### qwen2.5-coder:7b
- Gets the structure right but misses edge cases
- Minimal input validation unless prompted
- Good at following schemas and structured output
- Fast enough for iteration (generate → review → fix → regenerate)

### qwen3-coder:30b-a3b
- Better separation of concerns (uses dataclasses, proper class hierarchy)
- Good documentation and type hints
- Consistently puts sleep/await inside locks (addressed by anti-patterns skill)
- Cleanup methods are often stubs
- Worth the speed tradeoff for anything involving concurrency, auth, or architecture

### qwen3:8b
- Strong instruction-following for natural language tasks
- Good multilingual support (useful for i18n)
- Not code-specialized — don't use for implementation
- Better tone/style control than coding models
