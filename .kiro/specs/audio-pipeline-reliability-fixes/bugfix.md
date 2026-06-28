# Bugfix Requirements Document

## Introduction

The YouTube Vocal Harvester has multiple reliability and correctness issues across its audio pipeline. The critical failure is that the app depends entirely on 9 public Cobalt API instances for downloading YouTube audio — these go offline frequently, causing 500 errors on preview and harvest. Additional bugs include a race condition where the server accepts requests before FFmpeg detection completes, processing options that are displayed but never applied, a library playback toggle that sends empty parameters triggering invalid API requests, stale/corrupted audio cache files that are never invalidated, and documentation that is severely out of sync with the actual implementation.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN all 9 public Cobalt API instances are down or unreachable within the 4-second timeout THEN the system returns a 500 error on `/api/audio-stream` and `/api/harvest` with no fallback to local audio downloading

1.2 WHEN the server starts and an HTTP request arrives at `/api/audio-stream` or `/api/harvest` before the async `detectFFmpeg()` call resolves THEN the system rejects the request because `hasFFmpeg` is still `false`, even though FFmpeg is installed

1.3 WHEN a user enables normalization or fade in/out processing options in the TranscriptAligner UI and harvests a segment THEN the system ignores those options and produces a raw FFmpeg slice with no `loudnorm` or `afade` filters applied

1.4 WHEN a user enables Demucs voice isolation or WhisperX silence trimming options THEN the system displays these as functional toggles despite the underlying tools not being installed or integrated

1.5 WHEN a user clicks a currently-playing sample's waveform in the Library to stop playback THEN the system calls `onPreviewClip("", 0, 0, "", "")` which sets `activePreview` to an object with empty `videoId`, briefly mounting AcousticMonitor with invalid empty props and triggering an API request with empty videoId

1.6 WHEN a previously-downloaded audio file in `audio_cache/` is truncated or corrupted but exceeds 4000 bytes THEN the system serves the corrupted file indefinitely without validation, producing broken audio output

1.7 WHEN a developer reads the documentation files THEN the docs describe incorrect API response field names (`videos` instead of `results`, `segments` instead of `phrases`), incorrect request body fields (`text`/`duration` instead of `phraseText`/`endTime`), incorrect DB schema (`jobs`+`samples` object instead of `samples`+`tags` arrays), incorrect React version (18 instead of 19), and reference unimplemented features (Demucs, WhisperX) as functional

### Expected Behavior (Correct)

2.1 WHEN Cobalt instances are unavailable THEN the system SHALL download YouTube audio using a local solution (such as `yt-dlp` via child process or a Node.js YouTube download library) that does not depend on external third-party services

2.2 WHEN the server starts THEN the system SHALL await `detectFFmpeg()` completion inside `startServer()` before calling `app.listen()`, ensuring `hasFFmpeg` is accurately set before any requests are accepted

2.3 WHEN a user enables normalization and harvests a segment THEN the system SHALL apply the FFmpeg `loudnorm` filter to the output WAV; WHEN a user enables fade in/out THEN the system SHALL apply FFmpeg `afade` filters (fade in 0.05s at start, fade out 0.05s at end) to the output WAV

2.4 WHEN Demucs voice isolation or WhisperX silence trimming options are displayed THEN the system SHALL clearly label them as "coming soon" or disabled, preventing users from toggling unavailable features as if they were functional

2.5 WHEN a user clicks a currently-playing sample's waveform in the Library to stop playback THEN the system SHALL set `activePreview` to `null` (closing AcousticMonitor) rather than setting it to an object with empty `videoId`

2.6 WHEN a cached audio file exists in `audio_cache/` THEN the system SHALL validate it by checking that it exceeds a minimum size threshold of 100KB and passes an FFmpeg probe verification before serving it; invalid files SHALL be deleted and re-downloaded

2.7 WHEN a developer reads the documentation THEN the docs SHALL accurately reflect the current implementation: response field `results` (not `videos`), transcript response field `phrases` (not `segments`), request body fields `phraseText`/`endTime` (not `text`/`duration`), DB schema `{ samples: [], tags: [] }` with normalized tag table, React 19 (not 18), and unimplemented features clearly marked or removed

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a valid cached audio file exists in `audio_cache/` that is not corrupted THEN the system SHALL CONTINUE TO serve it from cache without re-downloading

3.2 WHEN FFmpeg is available and a valid local audio file exists THEN the system SHALL CONTINUE TO slice segments using sample-accurate seeking with `-ss` after `-i` producing mono 16-bit 44.1kHz WAV output

3.3 WHEN no processing options are enabled (all toggles off) THEN the system SHALL CONTINUE TO produce a raw FFmpeg slice identical to current behavior

3.4 WHEN a user clicks a non-playing sample's waveform in the Library THEN the system SHALL CONTINUE TO initiate preview playback by calling `onPreviewClip` with the sample's valid videoId, startTime, endTime, phraseText, and sourceTitle

3.5 WHEN the YouTube search, transcript retrieval, sample deletion, tag management, or library browsing APIs are called THEN the system SHALL CONTINUE TO function identically to current behavior

3.6 WHEN `generateVocalSynthWav` is called as a fallback for cases where neither the local downloader nor FFmpeg is available THEN the system SHALL CONTINUE TO produce a synthesized WAV buffer as a last-resort audio source

3.7 WHEN a sample is harvested with valid parameters and no processing options THEN the system SHALL CONTINUE TO save the sample to the JSON database with the same schema (`{ samples: [], tags: [] }`) and file structure (`harvested_samples/`)
