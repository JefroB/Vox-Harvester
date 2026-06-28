# Audio Pipeline Reliability Fixes — Bugfix Design

## Overview

The YouTube Vocal Harvester has seven interrelated reliability and correctness bugs spanning the audio download pipeline, server startup sequencing, audio processing, UI state management, cache integrity, and documentation. This design formalizes each bug condition, defines the expected correct behavior, hypothesizes root causes based on code analysis, and outlines a targeted fix strategy that preserves all existing working behavior.

The fix approach is:
1. Add a local `yt-dlp` fallback for audio downloading when Cobalt instances are unavailable
2. Await FFmpeg detection before accepting HTTP traffic
3. Apply `loudnorm` and `afade` FFmpeg filters when processing options are enabled
4. Disable Demucs/WhisperX toggles with "coming soon" labels
5. Set `activePreview` to `null` instead of an empty-field object when stopping playback
6. Validate cached audio files with size threshold and FFmpeg probe before serving
7. Correct all documentation inaccuracies

## Glossary

- **Bug_Condition (C)**: The set of conditions under which any of the seven bugs manifests — Cobalt unavailability, early request arrival, enabled-but-ignored processing options, empty preview params, corrupted cache, or stale docs
- **Property (P)**: The desired correct behavior for each bug condition — local download fallback, startup gating, applied filters, disabled toggles, null preview state, validated cache, accurate docs
- **Preservation**: All existing working behaviors that must remain unchanged — valid cache serving, FFmpeg slicing, raw harvest without options, normal preview initiation, search/transcript/tag/delete APIs, synth fallback, DB schema
- **`ensureLocalFullAudio`**: Function in `server.ts` that downloads and caches full YouTube audio via Cobalt
- **`harvestRealAudio`**: Function in `server.ts` that slices cached audio into WAV segments via FFmpeg
- **`handleTogglePlay`**: Method in `Library.tsx` that toggles playback by calling `onPreviewClip` with either valid params or empty strings
- **`activePreview`**: State in `App.tsx` controlling AcousticMonitor visibility and API request params

## Bug Details

### Bug Condition

The bugs manifest across seven distinct conditions that share a common theme: the system presents capabilities it cannot deliver, accepts work before it's ready, or serves invalid data without validation.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SystemEvent
  OUTPUT: boolean

  RETURN (input.type == "audio_download" AND allCobaltInstancesUnavailable())
         OR (input.type == "http_request" AND serverStarting AND NOT ffmpegDetectionComplete)
         OR (input.type == "harvest" AND input.options.normalization == true AND filterNotApplied("loudnorm"))
         OR (input.type == "harvest" AND input.options.fadeInOut == true AND filterNotApplied("afade"))
         OR (input.type == "toggle_option" AND input.option IN ["voiceIsolation", "silenceTrimming"] AND toolNotInstalled(input.option))
         OR (input.type == "stop_playback" AND activePreview != null AND resultingVideoId == "")
         OR (input.type == "serve_cache" AND cacheFileExists(input.videoId) AND (fileSize < 100KB OR ffprobeInvalid(input.path)))
         OR (input.type == "read_docs" AND docContent != implementationBehavior)
END FUNCTION
```

### Examples

- **Bug 1.1**: User clicks "Preview Cut" → server calls all 9 Cobalt instances → all timeout after 4s → `Promise.any` rejects → 500 error returned → no audio plays. With fix: yt-dlp downloads the audio locally as fallback.
- **Bug 1.2**: Server starts → `detectFFmpeg()` fires asynchronously → 200ms later a request hits `/api/harvest` → `hasFFmpeg` is still `false` → harvest fails even though FFmpeg is installed. With fix: server doesn't listen until detection completes.
- **Bug 1.3**: User enables "LUF Normalization" + "Linear Fades" → clicks "Harvest WAV" → server receives `options: { normalization: true, fadeInOut: true }` → `harvestRealAudio` ignores options entirely → produces raw slice. With fix: FFmpeg command includes `loudnorm` and `afade` filters.
- **Bug 1.4**: User toggles "Demucs Isolation" ON → expects voice separation → harvest runs without any separation model → user gets raw audio believing it was processed. With fix: toggles show "coming soon" and are non-functional.
- **Bug 1.5**: User clicks playing sample waveform in Library → `onPreviewClip("", 0, 0, "", "")` called → `activePreview` set to `{ videoId: "", ... }` → AcousticMonitor mounts → fetches `/api/audio-stream?videoId=&start=0&end=0` → 400 error. With fix: sets `activePreview` to `null`.
- **Bug 1.6**: Cached file `abc123_full.mp3` is 5KB (truncated download) → `ensureLocalFullAudio` checks `size > 4000` → passes → corrupted file served → broken audio output. With fix: minimum 100KB threshold + FFmpeg probe validation.
- **Bug 1.7**: Developer reads `API_REFERENCE.md` → sees response field `videos` → actual API returns `results` → developer writes broken client code. With fix: docs corrected to match implementation.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Valid cached audio files (>100KB, passing probe) must continue to be served from cache without re-downloading
- FFmpeg slicing with sample-accurate seeking (`-ss` after `-i`) must continue producing mono 16-bit 44.1kHz WAV output
- When no processing options are enabled, harvest must produce a raw FFmpeg slice identical to current behavior
- Normal preview initiation (clicking a non-playing sample) must continue calling `onPreviewClip` with valid params
- YouTube search, transcript retrieval, sample deletion, tag management, and library browsing APIs must continue functioning identically
- `generateVocalSynthWav` fallback must continue producing synthesized WAV buffers when neither local downloader nor FFmpeg is available
- Harvested samples must continue saving to the JSON database with schema `{ samples: [], tags: [] }` and file structure `harvested_samples/`

**Scope:**
All inputs that do NOT match the bug conditions should be completely unaffected by these fixes. This includes:
- Successful Cobalt downloads (when at least one instance responds)
- Requests arriving after FFmpeg detection is complete
- Harvests with all processing options disabled
- Normal preview playback initiation with valid videoId
- Serving valid, non-corrupted cached audio files
- Any API endpoint not related to audio-stream or harvest

## Hypothesized Root Cause

Based on code analysis, the confirmed root causes are:

1. **No Local Download Fallback (Bug 1.1)**: `ensureLocalFullAudio` → `getYouTubeAudioUrl` uses only Cobalt instances with `Promise.any`. When all 9 instances fail (common occurrence), the entire download path throws with no alternative. There is no `yt-dlp` or equivalent local tool integration.

2. **Fire-and-Forget FFmpeg Detection (Bug 1.2)**: Line ~54 of `server.ts` calls `detectFFmpeg()` without `await` at module scope. The `startServer()` function never awaits it before calling `app.listen()`. Requests arriving in the ~100-500ms detection window see `hasFFmpeg = false`.

3. **Options Received But Never Used (Bug 1.3)**: The `/api/harvest` endpoint destructures `options` from the request body and stores it in the job object, but the actual `harvestRealAudio(videoId, startTime, duration, localAudioPath)` call takes no options parameter. The FFmpeg command is always a plain slice with no filters.

4. **Unimplemented Feature Toggles (Bug 1.4)**: `TranscriptAligner.tsx` renders Demucs and Silence Trimming checkboxes as fully interactive. The `ProcessingOptions` interface includes `voiceIsolation` and `silenceTrimming` fields. The server stores them but never acts on them — no Demucs binary, no Python subprocess, no silence detection logic exists.

5. **Empty String Instead of Null (Bug 1.5)**: `Library.tsx` `handleTogglePlay` calls `onPreviewClip?.("", 0, 0, "", "")` to stop playback. In `App.tsx`, `handlePreviewClip` unconditionally sets `setActivePreview({ videoId, startTime, endTime, phraseText, sourceTitle })`. Since `activePreview` is not null, `AcousticMonitor` renders and constructs a URL with empty `videoId`.

6. **Insufficient Cache Validation (Bug 1.6)**: `ensureLocalFullAudio` checks only `fs.statSync(fullAudioPath).size > 4000`. A truncated HTTP download (network interruption) can easily produce a file >4KB but <100KB that is not a valid audio file. No content verification (FFmpeg probe) is performed.

7. **Documentation Never Updated (Bug 1.7)**: The docs were likely written early in development. The actual implementation evolved (field renames, schema changes, React version bump) but docs were never synchronized.

## Correctness Properties

Property 1: Bug Condition — Local Audio Download Fallback

_For any_ audio download request where all Cobalt API instances are unavailable (timeout, error, or offline), the fixed `ensureLocalFullAudio` function SHALL successfully download the audio using a local `yt-dlp` child process as a fallback, producing a valid audio file in `audio_cache/`.

**Validates: Requirements 2.1**

Property 2: Bug Condition — Server Startup Gating

_For any_ HTTP request arriving at the server, the fixed startup sequence SHALL guarantee that `hasFFmpeg` reflects the actual system state because `detectFFmpeg()` completed before `app.listen()` was called.

**Validates: Requirements 2.2**

Property 3: Bug Condition — Processing Options Applied

_For any_ harvest request where `options.normalization` is `true`, the fixed `harvestRealAudio` function SHALL include the FFmpeg `loudnorm` filter in the command; _for any_ harvest request where `options.fadeInOut` is `true`, the function SHALL include `afade` filters (fade in 0.05s, fade out 0.05s).

**Validates: Requirements 2.3**

Property 4: Bug Condition — Unimplemented Features Disabled

_For any_ UI rendering of Demucs voice isolation or WhisperX silence trimming options, the fixed component SHALL display these toggles as visually disabled with a "coming soon" indicator, preventing user interaction.

**Validates: Requirements 2.4**

Property 5: Bug Condition — Stop Playback Sets Null

_For any_ user action that stops playback of a currently-playing sample in the Library, the fixed `handleTogglePlay` SHALL call `onClose` or the equivalent mechanism that sets `activePreview` to `null`, causing AcousticMonitor to unmount without triggering an API request with empty parameters.

**Validates: Requirements 2.5**

Property 6: Bug Condition — Cache Validation

_For any_ cached audio file accessed by `ensureLocalFullAudio`, the fixed function SHALL validate that the file exceeds 100KB in size AND passes an FFmpeg probe verification before serving it; files failing validation SHALL be deleted and re-downloaded.

**Validates: Requirements 2.6**

Property 7: Preservation — Existing Behavior Unchanged

_For any_ input where none of the bug conditions hold (valid Cobalt response, post-startup requests, no processing options, normal preview initiation, valid cache files, non-doc operations), the fixed system SHALL produce exactly the same behavior as the original system, preserving all existing functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

**File**: `server.ts`

**Function**: `startServer` / module-level initialization

**Specific Changes**:

1. **Await FFmpeg Detection (Bug 1.2)**: Move `detectFFmpeg()` call inside `startServer()` and `await` it before `app.listen()`. Remove the fire-and-forget call at module level.

2. **Add yt-dlp Fallback (Bug 1.1)**: In `ensureLocalFullAudio`, wrap the Cobalt download in a try/catch. On failure, attempt `yt-dlp` via `execPromise` as a child process:
   ```
   yt-dlp -x --audio-format mp3 --audio-quality 128K -o "<outputPath>" "https://www.youtube.com/watch?v=<videoId>"
   ```
   If yt-dlp is also unavailable, throw the original error.

3. **Apply Processing Options in Harvest (Bug 1.3)**: Modify `harvestRealAudio` to accept an `options: ProcessingOptions` parameter. Build the FFmpeg filter chain conditionally:
   - If `normalization`: add `-af loudnorm=I=-14:TP=-1:LRA=11`
   - If `fadeInOut`: add `-af afade=t=in:st=0:d=0.05,afade=t=out:st=<end-0.05>:d=0.05`
   - Combine multiple filters with comma separation in `-af`

4. **Validate Cache Files (Bug 1.6)**: In `ensureLocalFullAudio`, change the cache validity check from `size > 4000` to `size > 102400` (100KB). Additionally, run a quick FFmpeg probe:
   ```
   ffmpeg -v error -i "<cachePath>" -f null -
   ```
   If probe exits with non-zero, delete the cached file and re-download.

5. **Detect yt-dlp Availability**: Add a `detectYtDlp()` function similar to `detectFFmpeg()` that checks for `yt-dlp --version`. Store result in `hasYtDlp` boolean. Await during startup.

---

**File**: `src/components/Library.tsx`

**Function**: `handleTogglePlay`

**Specific Changes**:

6. **Fix Stop Playback (Bug 1.5)**: When the sample is currently playing (toggle off), instead of calling `onPreviewClip?.("", 0, 0, "", "")`, introduce and call a separate `onStopPreview` callback prop (or a convention where `onPreviewClip` with no args signals stop). The simplest fix: in `App.tsx`, check if `videoId` is empty in `handlePreviewClip` and set `activePreview` to `null` instead of creating an object with empty fields.

---

**File**: `src/components/TranscriptAligner.tsx`

**Function**: Component render (processing plugins section)

**Specific Changes**:

7. **Disable Unimplemented Toggles (Bug 1.4)**: For `voiceIsolation` and `silenceTrimming` checkboxes:
   - Add `disabled` attribute
   - Add visual "Coming Soon" badge next to the label
   - Set `opacity-50 cursor-not-allowed` styles
   - Remove onChange handler (or make it no-op)

---

**File**: `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, `docs/ALIGNMENT_AND_SLICING.md`

**Specific Changes**:

8. **Fix Documentation (Bug 1.7)**:
   - Response field `videos` → `results`
   - Transcript response field `segments` → `phrases`
   - Request body fields `text`/`duration` → `phraseText`/`endTime`
   - DB schema: document actual `{ samples: [], tags: [] }` with normalized tag table
   - React version: 18 → 19
   - Mark Demucs/WhisperX as "planned" / "coming soon", not functional
   - Fix thumbnail URL field name and format

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify each fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that exercise each bug condition on the current unfixed code to observe failures and validate our root cause understanding.

**Test Cases**:
1. **Cobalt Unavailability Test**: Mock all 9 Cobalt instances as unreachable → call `ensureLocalFullAudio` → assert it throws with no fallback (will fail on unfixed code)
2. **Race Condition Test**: Call `/api/harvest` immediately after server starts without awaiting `detectFFmpeg` → assert `hasFFmpeg` is `false` even with FFmpeg installed (will fail on unfixed code)
3. **Processing Options Ignored Test**: Call `/api/harvest` with `options.normalization: true` → inspect FFmpeg command → assert `loudnorm` filter is absent (will fail on unfixed code)
4. **Empty Preview Params Test**: Simulate `handleTogglePlay` on a playing sample → assert `activePreview` is set to object with empty `videoId` triggering invalid API request (will fail on unfixed code)
5. **Cache Validation Test**: Create a 5KB truncated file in `audio_cache/` → call `ensureLocalFullAudio` → assert corrupted file is served without validation (will fail on unfixed code)

**Expected Counterexamples**:
- `ensureLocalFullAudio` throws "Unable to resolve active direct YouTube audio stream link" with no recovery path
- `hasFFmpeg` is `false` during first ~200ms of server life despite FFmpeg being installed
- FFmpeg command string contains no `-af` filter regardless of options
- `activePreview` becomes `{ videoId: "", startTime: 0, endTime: 0, ... }` instead of `null`
- Cache check passes for any file >4000 bytes regardless of content validity

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT expectedBehavior(result)
END FOR
```

Specifically:
- For Cobalt failures: assert yt-dlp fallback produces valid audio file
- For startup: assert `hasFFmpeg` is correctly set before first request accepted
- For options: assert FFmpeg command includes correct filters when options are enabled
- For playback stop: assert `activePreview` becomes `null`
- For cache: assert corrupted files are deleted and re-downloaded

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for valid inputs (successful Cobalt downloads, post-startup requests, harvests without options, normal preview playback, valid cache files), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Valid Cache Preservation**: Generate random valid audio files (>100KB, valid headers) → assert they are served from cache without re-download after fix
2. **Raw Harvest Preservation**: Generate harvest requests with all options `false` → assert FFmpeg command is identical to current behavior (no filters added)
3. **Normal Preview Preservation**: Generate valid `onPreviewClip` calls with non-empty videoId → assert `activePreview` is set to proper object (not null)
4. **API Endpoint Preservation**: Generate valid search/transcript/delete/tag requests → assert response shape and status codes are unchanged
5. **FFmpeg Slice Format Preservation**: Generate random valid startTime/duration pairs → assert output is always mono 16-bit 44.1kHz WAV

### Unit Tests

- Test `ensureLocalFullAudio` with mocked Cobalt failure and mocked yt-dlp success
- Test `ensureLocalFullAudio` cache validation with files at various sizes (4KB, 50KB, 100KB, 1MB)
- Test `harvestRealAudio` FFmpeg command construction with all option combinations
- Test `handlePreviewClip` in App.tsx with empty videoId → assert null
- Test `handleTogglePlay` in Library for playing vs non-playing samples
- Test startup sequence timing (FFmpeg detected before listen)
- Test disabled state of Demucs/WhisperX toggles

### Property-Based Tests

- Generate random `ProcessingOptions` objects → verify FFmpeg command includes correct filters for each enabled option and no filters when all disabled
- Generate random videoId + startTime + duration combinations → verify FFmpeg command format is always valid and preserves mono 16-bit 44.1kHz output spec
- Generate random file sizes → verify cache validation correctly accepts files ≥100KB and rejects files <100KB
- Generate random preview clip parameters → verify `activePreview` is null when videoId is empty, and a valid object when videoId is non-empty

### Integration Tests

- Test full harvest flow: Cobalt down → yt-dlp fallback → FFmpeg slice with normalization → valid WAV in `harvested_samples/`
- Test server cold start → immediate request → verify request waits for FFmpeg detection (or server isn't listening yet)
- Test Library playback toggle cycle: start → stop → start → verify no invalid API requests fired
- Test cache invalidation end-to-end: corrupt file exists → request audio → file deleted → re-downloaded → valid audio served
