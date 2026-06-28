---
name: Code Comments
tags: [code, docs]
description: Standards for inline code documentation — docstrings, annotations, and explanatory comments that help both humans and agents understand intent.
---

# Code Comments

## Core Principle

Comments exist to convey **intent and reasoning** — the *why* behind code. The code itself shows *what* and *how*. Good comments fill the gap that code alone cannot.

## 1. What MUST Be Documented

### Public API Surface

Every exported function, class, method, type, and constant MUST have a doc comment covering:

- **Purpose** — one-line summary of what it does
- **Parameters** — name, type, constraints, defaults
- **Returns** — type and meaning (not just "returns a string")
- **Throws/Errors** — conditions that cause failure
- **Side effects** — state mutations, I/O, emitted events

```typescript
/**
 * Slice an audio segment from the master file with sample-accurate seeking.
 *
 * Uses post-input seeking (-ss after -i) to ensure microsecond precision
 * at the cost of decoding from file start. For files >1hr, consider
 * chunked pre-processing instead.
 *
 * @param masterPath - Absolute path to the source audio file
 * @param startMs - Start time in milliseconds (inclusive)
 * @param durationMs - Duration to extract in milliseconds
 * @returns Absolute path to the sliced WAV output file
 * @throws SliceError if ffmpeg exits non-zero or input file is missing
 */
export async function sliceAudio(
  masterPath: string,
  startMs: number,
  durationMs: number
): Promise<string> {
```

### Non-Obvious Logic

Any code where the *why* is not immediately apparent from reading:

- Workarounds for library bugs or platform quirks
- Performance-motivated deviations from the "obvious" approach
- Business rules that encode domain knowledge
- Magic numbers (must be named constants or explained)

```typescript
// YouTube transcript cues often arrive with overlapping timestamps.
// We merge cues with <200ms gaps to prevent micro-fragments that
// sound unnatural when played back individually.
const GAP_MERGE_THRESHOLD_MS = 200;
```

### Module-Level Context

Each source file should have a brief header comment explaining:
- What this module is responsible for
- Its role in the larger system (one sentence)
- Key dependencies or assumptions

```typescript
/**
 * Transcript grouping and normalization.
 *
 * Takes raw YouTube caption cues and merges them into natural spoken phrases
 * suitable for audio slicing. Downstream consumers expect grouped phrases
 * with consolidated timestamps and cleaned text.
 */
```

## 2. Internal / Unexported Code

- One-line summary is sufficient for helpers
- Complex private functions still deserve full docs if the logic is tricky
- Use `@internal` tag for functions exported solely for testing

## 3. Comment Style

### Format (TypeScript/JavaScript)

- Use `/** */` JSDoc blocks for functions, classes, methods
- Use `//` for inline explanations within function bodies
- Use `// ---` section separators sparingly for long files

### Tone

- Write in present tense, imperative mood
- Be concise — one sentence is often enough
- Avoid redundancy with the function signature (don't restate types)

### Bad vs Good

```typescript
// ❌ Restates the obvious — adds no value
/** Set the volume level. */
function setVolume(level: number): void {

// ✅ Explains constraint the signature doesn't convey
/** Set playback volume. Clamps to 0–1 range; values outside are normalized. */
function setVolume(level: number): void {
```

```typescript
// ❌ Stale comment — code changed, comment didn't
// Fetch user by email
function fetchUserById(id: string): Promise<User> {

// ✅ Accurate and adds context
// Fetches user record with profile eagerly loaded (avoids N+1 in caller)
function fetchUserById(id: string): Promise<User> {
```

## 4. When to Update Comments

- **Modified behavior** → update the docstring in the same commit
- **Renamed function** → update any `@see` or cross-references
- **Removed function** → search for references in other comments and docs
- **Changed parameters** → update `@param` entries immediately

## 5. Anti-Patterns

- ❌ `/** TODO: document this */` — placeholder comments that never get filled
- ❌ Commented-out code left in place — use version control instead
- ❌ Comments that describe *what* the next line does when it's already clear from the code
- ❌ Lying comments — code changed but comment still describes old behavior
- ❌ Excessive inline comments that interrupt reading flow (every other line)
- ❌ `@author` tags — use git blame for attribution

## 6. Agentic Context

Comments are critical for AI agents working on the codebase:

- Agents use comments to understand intent without reading entire call chains
- Well-documented modules reduce token consumption during exploration
- A docstring with constraints (e.g., "must be called after init") prevents agents from introducing ordering bugs
- `@internal` tags signal agents not to use a function in new code

Write comments as if the next reader has zero project history — because they might be an agent encountering this file for the first time.
