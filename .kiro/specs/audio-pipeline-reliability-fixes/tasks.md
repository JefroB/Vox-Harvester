# Implementation Plan

## Overview

This task list implements the audio pipeline reliability fixes using the exploratory bugfix workflow: write tests to confirm bugs exist, write preservation tests to capture current correct behavior, implement all seven fixes, then validate everything passes.

## Tasks

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - Audio Pipeline Reliability Failures
  - **IMPORTANT**: Write these property-based tests BEFORE implementing any fixes
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fixes when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate each bug exists in the current codebase
  - **Scoped PBT Approach**: Scope properties to concrete failing cases for each bug condition
  - Test 1 - Cobalt Unavailability: Mock all 9 Cobalt instances as unreachable → call `ensureLocalFullAudio` → assert it falls back to local download producing a valid file (currently throws with no fallback)
  - Test 2 - FFmpeg Race Condition: Simulate request arriving before `detectFFmpeg()` resolves → assert `hasFFmpeg` reflects true system state (currently `false` during startup window)
  - Test 3 - Processing Options Ignored: Call harvest with `options.normalization: true` and `options.fadeInOut: true` → inspect FFmpeg command → assert `loudnorm` and `afade` filters are present (currently absent)
  - Test 4 - Empty Preview Params: Simulate `handleTogglePlay` on a currently-playing sample → assert `activePreview` becomes `null` (currently becomes `{ videoId: "", ... }`)
  - Test 5 - Cache Validation: Create truncated files (5KB, 50KB) in `audio_cache/` → call `ensureLocalFullAudio` → assert corrupted files are rejected and re-downloaded (currently served if >4KB)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: All tests FAIL (this is correct - it proves each bug exists)
  - Document counterexamples found:
    - `ensureLocalFullAudio` throws "Unable to resolve active direct YouTube audio stream link" with no recovery
    - `hasFFmpeg` is `false` during first ~200ms despite FFmpeg being installed
    - FFmpeg command contains no `-af` filter regardless of options passed
    - `activePreview` becomes `{ videoId: "", startTime: 0, endTime: 0, ... }` instead of `null`
    - Cache check passes for any file >4000 bytes regardless of content validity
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_
  - [local-coder: --tags code test --complexity complex --context server.ts src/App.tsx src/components/Library.tsx --output tests/test_bug_conditions.py]

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Audio Pipeline Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Step 1 - Observe on UNFIXED code**:
    - Observe: valid cached audio files (>100KB, valid headers) are served from cache without re-download
    - Observe: FFmpeg slice with no options produces raw mono 16-bit 44.1kHz WAV (no filters in command)
    - Observe: `onPreviewClip` with valid non-empty videoId sets `activePreview` to proper object
    - Observe: YouTube search, transcript, deletion, tag APIs return expected response shapes
    - Observe: `generateVocalSynthWav` fallback produces synthesized WAV buffer
    - Observe: harvested samples save to JSON DB with schema `{ samples: [], tags: [] }` in `harvested_samples/`
  - **Step 2 - Write property-based tests capturing observed behavior**:
    - Property: For all valid cached audio files (size ≥100KB, valid audio content), file is served from cache without triggering download
    - Property: For all harvest requests with all options `false`, FFmpeg command is a plain slice with no `-af` filters, output is mono 16-bit 44.1kHz WAV
    - Property: For all `onPreviewClip` calls with non-empty videoId and valid params, `activePreview` is set to a valid object (not null)
    - Property: For random valid startTime/duration pairs, FFmpeg command always uses sample-accurate seeking (`-ss` after `-i`)
    - Property: For all harvest requests with valid params and no options, sample saves to DB with correct schema
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: All tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [local-coder: --tags code test --complexity complex --context server.ts src/App.tsx src/components/Library.tsx --output tests/test_preservation.py]

- [x] 3. Fix for audio pipeline reliability failures

  - [x] 3.1 Await FFmpeg detection before accepting traffic (Bug 1.2)
    - Move `detectFFmpeg()` call inside `startServer()` function
    - Add `await` before `detectFFmpeg()` so it completes before `app.listen()`
    - Remove fire-and-forget call at module level (~line 54 of `server.ts`)
    - Ensure `hasFFmpeg` is accurately set before any HTTP requests are accepted
    - _Bug_Condition: input.type == "http_request" AND serverStarting AND NOT ffmpegDetectionComplete_
    - _Expected_Behavior: hasFFmpeg reflects actual system state before first request accepted_
    - _Preservation: All existing endpoint behavior unchanged after startup completes_
    - _Requirements: 2.2_
    - [local-coder: --tags code --complexity simple --context server.ts --output server.ts --scope startServer]

  - [x] 3.2 Add yt-dlp detection and local download fallback (Bug 1.1)
    - Add `detectYtDlp()` function similar to `detectFFmpeg()` that checks `yt-dlp --version`
    - Store result in `hasYtDlp` boolean
    - Await `detectYtDlp()` during startup alongside FFmpeg detection
    - In `ensureLocalFullAudio`, wrap Cobalt download in try/catch
    - On Cobalt failure, if `hasYtDlp` is true, attempt download via child process: `yt-dlp -x --audio-format mp3 --audio-quality 128K -o "<outputPath>" "https://www.youtube.com/watch?v=<videoId>"`
    - If yt-dlp also unavailable, throw the original Cobalt error
    - _Bug_Condition: input.type == "audio_download" AND allCobaltInstancesUnavailable()_
    - _Expected_Behavior: yt-dlp fallback produces valid audio file in audio_cache/_
    - _Preservation: Successful Cobalt downloads continue to work as primary path; generateVocalSynthWav fallback unchanged_
    - _Requirements: 2.1_
    - [local-coder: --tags code --complexity complex --context server.ts --output server.ts --scope detectYtDlp,ensureLocalFullAudio]

  - [x] 3.3 Implement cache validation with size threshold and FFmpeg probe (Bug 1.6)
    - Change cache validity check from `size > 4000` to `size > 102400` (100KB minimum)
    - Add FFmpeg probe validation: run `ffmpeg -v error -i "<cachePath>" -f null -`
    - If probe exits non-zero OR file <100KB, delete cached file and trigger re-download
    - Ensure valid cached files (≥100KB, passing probe) continue to be served without re-download
    - _Bug_Condition: input.type == "serve_cache" AND (fileSize < 100KB OR ffprobeInvalid(path))_
    - _Expected_Behavior: Invalid files deleted and re-downloaded; valid files served from cache_
    - _Preservation: Valid cached audio files (>100KB, passing probe) served from cache without re-downloading_
    - _Requirements: 2.6, 3.1_
    - [local-coder: --tags code --complexity simple --context server.ts --output server.ts --scope ensureLocalFullAudio]

  - [x] 3.4 Apply processing options in harvestRealAudio (Bug 1.3)
    - Modify `harvestRealAudio` signature to accept `options: ProcessingOptions` parameter
    - Update `/api/harvest` endpoint to pass `options` to `harvestRealAudio`
    - Build FFmpeg filter chain conditionally:
      - If `normalization` is true: add `-af loudnorm=I=-14:TP=-1:LRA=11`
      - If `fadeInOut` is true: add `-af afade=t=in:st=0:d=0.05,afade=t=out:st=<end-0.05>:d=0.05`
      - Combine multiple filters with comma separation in single `-af` argument
    - When no options are enabled, produce raw FFmpeg slice identical to current behavior (no `-af` flag)
    - _Bug_Condition: input.type == "harvest" AND (options.normalization == true OR options.fadeInOut == true) AND filterNotApplied_
    - _Expected_Behavior: FFmpeg command includes loudnorm/afade filters matching enabled options_
    - _Preservation: Harvests with all options disabled produce identical raw slice; mono 16-bit 44.1kHz WAV output preserved_
    - _Requirements: 2.3, 3.2, 3.3_
    - [local-coder: --tags code --complexity complex --context server.ts --output server.ts --scope harvestRealAudio]

  - [x] 3.5 Fix stop playback to set activePreview to null (Bug 1.5)
    - In `App.tsx` `handlePreviewClip`: add guard at top — if `videoId` is empty string, set `activePreview` to `null` and return early
    - This prevents AcousticMonitor from mounting with invalid empty props
    - No API request with empty videoId will be triggered
    - Normal preview initiation (non-empty videoId) continues to set `activePreview` to valid object
    - _Bug_Condition: input.type == "stop_playback" AND activePreview != null AND resultingVideoId == ""_
    - _Expected_Behavior: activePreview becomes null, AcousticMonitor unmounts cleanly_
    - _Preservation: Clicking non-playing sample continues to initiate playback with valid params_
    - _Requirements: 2.5, 3.4_
    - [local-coder: --tags code --complexity simple --context src/App.tsx --output src/App.tsx --scope handlePreviewClip]

  - [x] 3.6 Disable unimplemented Demucs/WhisperX toggles (Bug 1.4)
    - In `TranscriptAligner.tsx`, for `voiceIsolation` and `silenceTrimming` checkboxes:
      - Add `disabled` attribute to prevent interaction
      - Add visual "Coming Soon" badge/label next to each toggle text
      - Apply `opacity-50 cursor-not-allowed` styles
      - Remove or no-op the onChange handler
    - Toggles remain visible but clearly indicate non-functional status
    - _Bug_Condition: input.type == "toggle_option" AND input.option IN ["voiceIsolation", "silenceTrimming"] AND toolNotInstalled_
    - _Expected_Behavior: Toggles displayed as disabled with "coming soon" indicator_
    - _Preservation: All other processing option toggles (normalization, fadeInOut) continue to function_
    - _Requirements: 2.4_
    - [local-coder: --tags code --complexity simple --context src/components/TranscriptAligner.tsx --output src/components/TranscriptAligner.tsx --scope voiceIsolation,silenceTrimming]

  - [x] 3.7 Correct documentation inaccuracies (Bug 1.7)
    - In `docs/API_REFERENCE.md`: response field `videos` → `results`, transcript field `segments` → `phrases`, request body `text`/`duration` → `phraseText`/`endTime`
    - In `docs/ARCHITECTURE.md`: DB schema → `{ samples: [], tags: [] }` with normalized tag table, React version 18 → 19
    - In `docs/README.md`: fix React version, fix any incorrect feature claims
    - In `docs/ALIGNMENT_AND_SLICING.md`: fix any incorrect field references
    - Mark Demucs/WhisperX as "planned" / "coming soon", not functional
    - Fix thumbnail URL field name and format if incorrect
    - _Bug_Condition: input.type == "read_docs" AND docContent != implementationBehavior_
    - _Expected_Behavior: Documentation accurately reflects current implementation_
    - _Preservation: No code behavior changes from documentation updates_
    - _Requirements: 2.7_
    - [cloud-only: documentation corrections require reading actual implementation to verify accuracy — local model hallucinates project details]

  - [x] 3.10 Add docstrings and inline comments to all new/modified functions
    - Add JSDoc docstring to `detectYtDlp()` explaining purpose, return type, and side effects
    - Add JSDoc docstring to updated `ensureLocalFullAudio()` documenting the Cobalt → yt-dlp fallback chain and cache validation logic
    - Add JSDoc docstring to updated `harvestRealAudio()` documenting the new `options` parameter and filter chain construction
    - Add inline `// why` comments at: cache size threshold (why 100KB), probe validation step, yt-dlp command flags, filter combination logic
    - Add JSDoc to `handlePreviewClip` in App.tsx documenting the empty-videoId guard behavior
    - Verify all existing docstrings on modified functions are still accurate post-fix
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_
    - [cloud-only: docstrings require reading actual implementation to ensure accuracy]

  - [x] 3.11 Update docs/ARCHITECTURE.md with new audio pipeline design
    - Document the yt-dlp fallback download path (Cobalt primary → yt-dlp secondary → synth fallback)
    - Document the cache validation strategy (100KB threshold + FFmpeg probe)
    - Document the processing options filter chain (loudnorm, afade)
    - Document the startup gating sequence (await detectFFmpeg + detectYtDlp before app.listen)
    - Update any existing audio pipeline diagrams or flow descriptions
    - Ensure `docs/README.md` index links remain valid
    - _Requirements: 2.1, 2.2, 2.3, 2.6_
    - [cloud-only: architecture docs require reading actual implementation to verify accuracy]

  - [x] 3.12 Verify no stale documentation references remain
    - Search docs/ for references to the old 4KB cache threshold
    - Search docs/ for references to Cobalt as the only download method
    - Search docs/ for any remaining claims that Demucs/WhisperX are functional
    - Search docs/ for old field names (videos, segments, text, duration) that should have been caught by 3.7
    - Verify `docs/README.md` index links all resolve to existing files
    - _Requirements: 2.7_
    - [cloud-only: stale doc detection requires cross-referencing with actual implementation]

  - [x] 3.8 Verify bug condition exploration tests now pass
    - **Property 1: Expected Behavior** - Audio Pipeline Reliability Fixes Validated
    - **IMPORTANT**: Re-run the SAME tests from task 1 - do NOT write new tests
    - The tests from task 1 encode the expected behavior for each bug condition
    - When these tests pass, it confirms all expected behaviors are satisfied:
      - Cobalt failure → yt-dlp fallback produces valid audio
      - Server startup → `hasFFmpeg` correctly set before first request
      - Processing options → FFmpeg command includes correct filters
      - Stop playback → `activePreview` becomes `null`
      - Cache validation → corrupted files rejected and re-downloaded
    - Run bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: All tests PASS (confirms bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_
    - [cloud-only: test execution and verification only — no code generation]

  - [x] 3.9 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Behavior Unchanged After Fixes
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: All tests PASS (confirms no regressions)
    - Confirm: valid cache still served, raw harvests unchanged, preview initiation works, APIs intact, DB schema preserved
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
    - [cloud-only: test execution and verification only — no code generation]

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite including exploration tests, preservation tests, and any existing unit/integration tests
  - Verify all bug condition tests pass (confirming fixes work)
  - Verify all preservation tests pass (confirming no regressions)
  - Verify no new lint/type errors introduced
  - Ask the user if questions arise or if integration testing with real yt-dlp/FFmpeg is needed
  - [cloud-only: checkpoint]


## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write exploration and preservation tests BEFORE implementing fixes"
    },
    {
      "wave": 2,
      "tasks": ["3.1", "3.2", "3.3"],
      "description": "Server startup and download pipeline fixes (sequential: await FFmpeg → yt-dlp fallback → cache validation)"
    },
    {
      "wave": 3,
      "tasks": ["3.4", "3.5", "3.6"],
      "description": "Processing options, playback state, and UI toggle fixes (parallelizable)"
    },
    {
      "wave": 4,
      "tasks": ["3.7", "3.10", "3.11", "3.12"],
      "description": "Documentation: fix inaccuracies, add docstrings to new code, update architecture docs, verify no stale refs"
    },
    {
      "wave": 5,
      "tasks": ["3.8", "3.9"],
      "description": "Re-run exploration and preservation tests to verify fixes and confirm no regressions"
    },
    {
      "wave": 6,
      "tasks": ["4"],
      "description": "Final checkpoint - ensure all tests pass"
    }
  ]
}
```

## Notes

- Tasks 1 and 2 MUST be completed before any implementation begins
- Task 1 tests are expected to FAIL on unfixed code (this confirms bugs exist)
- Task 2 tests are expected to PASS on unfixed code (this captures baseline behavior)
- Tasks 3.1–3.7 can be partially parallelized but server startup fixes (3.1, 3.2, 3.3) should be sequential
- Task 3.7 (documentation corrections) has no code impact and can be done last in its wave
- Tasks 3.10–3.12 (new docstrings, architecture update, stale ref check) MUST follow the code fixes since they document the new behavior
- yt-dlp must be installed on the system for Bug 1.1 fix to work at runtime
- Property-based tests use the Hypothesis framework (Python) already configured in the project
