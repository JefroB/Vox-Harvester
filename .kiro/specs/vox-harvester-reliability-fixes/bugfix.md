# Bugfix Requirements Document

## Introduction

The YouTube Vocal Harvester has seven identified bugs spanning reliability, correctness, and UX honesty. The most critical is the Cobalt downloader dependency — all public instances are unreliable/dead, making audio download the single point of failure. Additional bugs include a race condition in FFmpeg detection, cosmetic-only processing options that mislead users, API/database schema mismatches between docs and code, a frontend bug sending invalid requests to stop playback, and an insufficient cache validation threshold that permanently serves corrupted files.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the server attempts to download YouTube audio THEN the system relies exclusively on external Cobalt API instances that are frequently offline, causing audio preview and harvest to fail with 500 errors and no fallback to local solutions

1.2 WHEN all Cobalt instances fail within the 4-second timeout THEN the system returns a 500 error with no useful recovery path, despite `generateVocalSynthWav` existing as an unused fallback

1.3 WHEN the server module loads at startup THEN `detectFFmpeg()` is called without `await`, creating a race condition where `hasFFmpeg` remains `false` for early requests that arrive before the async detection completes

1.4 WHEN a user toggles processing options (Demucs isolation, silence trimming, normalization, fades) in the frontend THEN the server completely ignores these options — the FFmpeg command performs only a raw time-slice with no DSP processing applied

1.5 WHEN the frontend UI references "Demucs" voice isolation and "WhisperX" alignment THEN neither tool is installed, configured, or invoked anywhere in the backend, misleading users about actual capabilities

1.6 WHEN the `/api/search` endpoint returns results THEN the response uses `{ results }` but the API documentation specifies `{ videos }`

1.7 WHEN the `/api/transcripts` endpoint returns results THEN the response uses `{ phrases }` but the API documentation specifies `{ videoId, segments }`

1.8 WHEN the `/api/harvest` endpoint receives a request THEN the code expects `{ phraseText, endTime }` but the API documentation specifies `{ text, duration }`

1.9 WHEN the `/api/harvest` endpoint returns a response THEN the code returns only `{ jobId }` but the API documentation specifies `{ message, jobId, status }`

1.10 WHEN the database schema is examined THEN the code uses `{ samples: [], tags: [] }` with normalized separate tables, but the documentation describes `{ jobs: {...}, samples: {...} }` with nested tags inside sample objects

1.11 WHEN a user clicks a playing sample's waveform in Library.tsx to stop playback THEN the component dispatches `onPreviewClip?.("", 0, 0, "", "")` which causes AcousticMonitor to request `/api/audio-stream?videoId=&start=0&end=0`, resulting in a 400 error response

1.12 WHEN a master MP3 file exists in the audio cache with a size greater than 4000 bytes THEN the system considers it valid and serves it permanently, even if the file is corrupted or truncated (a partial download of a 5-minute audio file easily exceeds 4000 bytes)

### Expected Behavior (Correct)

2.1 WHEN the server attempts to download YouTube audio THEN the system SHALL use a local tool (yt-dlp binary) as the primary download mechanism, eliminating dependency on unreliable external Cobalt API services

2.2 WHEN the primary audio download mechanism fails THEN the system SHALL fall back to `generateVocalSynthWav` to produce a synthesized placeholder WAV, returning a usable audio response rather than a 500 error

2.3 WHEN the server starts up THEN the system SHALL await `detectFFmpeg()` completion before accepting HTTP requests, ensuring `hasFFmpeg` is correctly set before any request processing begins

2.4 WHEN a user selects processing options (normalization, fades, silence trimming) THEN the server SHALL apply the corresponding FFmpeg filters (loudnorm, afade, silenceremove) to the sliced audio output

2.5 WHEN the frontend UI displays DSP capability labels THEN it SHALL only reference tools that are actually installed and invoked, or SHALL clearly label unimplemented features as unavailable/planned

2.6 WHEN the `/api/search` endpoint returns results THEN the API documentation SHALL match the actual response shape used by the code (either update docs to say `{ results }` or update code to say `{ videos }`)

2.7 WHEN the `/api/transcripts` endpoint returns results THEN the API documentation SHALL match the actual response shape used by the code (either update docs to say `{ phrases }` or update code to say `{ videoId, segments }`)

2.8 WHEN the `/api/harvest` endpoint receives a request and returns a response THEN the API documentation SHALL match the actual field names used by the code (`phraseText`/`endTime` for request, and the actual response shape)

2.9 WHEN the `/api/harvest` endpoint returns a response THEN the code SHALL return `{ message, jobId, status }` matching user expectations of a queued job acknowledgment

2.10 WHEN the database schema documentation is reviewed THEN it SHALL accurately describe the actual normalized `{ samples: [], tags: [] }` structure used in code

2.11 WHEN a user clicks a playing sample's waveform in Library.tsx to stop playback THEN the system SHALL stop playback by setting `activePreview` to `null` directly (or using a dedicated stop signal) without dispatching an API request with empty/invalid parameters

2.12 WHEN validating cached master MP3 files THEN the system SHALL use a higher minimum size threshold proportional to expected content (e.g., ~50KB minimum for any valid audio file) and optionally verify the file begins with valid MP3/ID3 header bytes

### Unchanged Behavior (Regression Prevention)

3.1 WHEN yt-dlp or any local download succeeds THEN the system SHALL CONTINUE TO cache the full master MP3 locally in `audio_cache/` and reuse it for subsequent slice requests against the same video

3.2 WHEN FFmpeg is available and a valid cached master exists THEN the system SHALL CONTINUE TO perform sample-accurate slicing using `-ss` after `-i` for precision alignment

3.3 WHEN the youtube-transcript npm package successfully retrieves captions THEN the system SHALL CONTINUE TO use it as the primary transcript source with intelligent cue grouping

3.4 WHEN a harvest job completes successfully THEN the system SHALL CONTINUE TO write the sample record and tags to the JSON database and store the WAV file in `harvested_samples/`

3.5 WHEN the Library component initiates playback of a sample THEN the system SHALL CONTINUE TO pass `(videoId, startTime, endTime, phraseText, sourceTitle)` to the AcousticMonitor for audio streaming

3.6 WHEN the frontend fetches search results or transcripts THEN the system SHALL CONTINUE TO render them correctly regardless of which response field name is used (frontend code must stay in sync with backend)

3.7 WHEN processing options are not selected by the user THEN the system SHALL CONTINUE TO perform a clean raw time-slice without additional DSP, preserving the current fast-path behavior
