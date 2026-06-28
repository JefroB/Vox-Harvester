# System Architecture Overview

This document reviews the system architecture, directory layouts, database structure, and the concurrent multi-threaded execution pipelines of the YouTube Vocal Harvester.

---

## 🗺️ Data Flow Diagram

The diagram below outlines the full-stack pipeline from a user's initial YouTube search to the generation of a high-fidelity harvested sample:

```text
[ React SPA Client ]             [ Express API Server ]              [ External / OS Utilities ]
         │                                 │                                      │
         ├─ 1. Search Query ──────────────>│─ Search Youtube ────────────────────>│ [ YouTube Search Engine ]
         │  (Keywords)                     │  (Fetch Video Metadata list)         │
         │                                 │                                      │
         ├─ 2. Select Video ──────────────>│─ Retrieve Captions ──────────────────>│ [ YoutubeTranscript / API ]
         │  (Video ID)                     │  (Group cues to coherent phrases)    │
         │                                 │                                      │
         ├─ 3. Select Phrase & Offset ────>│─ Parallel Cobalt Request ───────────>│ [ Cobalt Downloader Pool ]
         │  (Triggers Stream or Harvest)   │  (Concurrent POST to resolve MP3 URL)│
         │                                 │                                      │
         │                                 │─ Cached Master MP3 ─────────────────>│ [ Local disk storage ]
         │                                 │  (audio_cache/video_id_full.mp3)     │
         │                                 │                                      │
         │                                 │─ Accurate FFmpeg Slicing ───────────>│ [ FFmpeg Binary Utility ]
         │                                 │  (WAV generation: -i input -ss)      │
         │                                 │                                      │
         │<─ 4. Stream Sliced WAV ─────────│─ Serve WAV ──────────────────────────┤
         │  (Audio Player & Canvas Peaks)  │  (Generate Waveform Visual Peaks)    │
         │                                 │                                      │
         ├─ 5. Harvest & Save ────────────>│─ Queue Background Job ───────────────┤
         │  (Tagging, custom details)      │  (Write entry to local JSON DB)      │
         │                                 │  (Move file to harvested_samples/)   │
         ▼                                 ▼                                      ▼
```

---

## 📂 Project Directory Structure

Understanding the layout of key files and directories:

* **`/` (Workspace Root)**
  * `server.ts` – The single backend server containing all API handlers, task queues, FFmpeg commands, and parallel downloader resolvers.
  * `vocal_harvester_db.json` – The primary persistent database, saving all harvested samples and tags.
  * `package.json` – Node dependency manifest. Dev environment runs via `tsx`, production compiles server code to `dist/server.cjs` via `esbuild`.
* **`/docs`** – System documentation and maintenance handbooks.
* **`/audio_cache`** – Holds full cached master `.mp3` files and temporary sliced `.wav` previews. *(Cleared of temporary WAV files on startup).*
* **`/harvested_samples`** – Stores finalized sample audio files (`.wav`), cataloged using their unique database ID.
* **`/src` (Frontend Source)**
  * `main.tsx` – React entrypoint.
  * `App.tsx` – Master layout. Manages global state, application navigation views, and step-by-step progress flags.
  * `types.ts` – Universal TypeScript types sharing schemas (e.g., `VideoMetadata`, `TranscriptSegment`, `HarvestJob`, `VocalSample`) between client and server APIs.
  * **`/src/components`**
    * `YoutubeSearch.tsx` – Step 1 UI. Connects search inputs, queries `/api/search`, and parses/displays returned results.
    * `TranscriptAligner.tsx` – Step 2 UI. Manages subtitle loading, phrase grouping display, manual start/end offset adjustment, processing option toggles, and trigger buttons for audio previews.
    * `AcousticMonitor.tsx` – Step 3 UI. Renders an interactive canvas waveform. Includes zoom, playback speed controls, audio playback synchronization, and a metadata tag editor.
    * `ActiveJobs.tsx` – Step 4 Queue. Tracks the status of ongoing audio extractions and lists errors.
    * `Library.tsx` – Saved catalog. Allows library search, filtering, audio playback of harvested clips, download actions, and direct custom tag editing.

---

## ⚡ Cobalt Downloader Parallel Routing

To achieve rapid, reliable audio downloads without proxy rotation costs, the backend implements a **Concurrent Parallel Cobalt Query Pool**:

1. A list of active, public Cobalt API endpoints is declared (e.g., `https://api.cobalt.tools`, `https://co.wukko.me`, etc.).
2. When a video audio track is required, the server fires **simultaneous POST requests** to all instances.
3. Every request instructs Cobalt to parse the YouTube video in `audio` mode, requesting a `128kbps` `mp3` stream.
4. Using `Promise.any()`, the backend captures the **first successful response** that resolves a direct audio streaming/download link.
5. The remaining slow or failing requests are immediately aborted using a short `AbortSignal` timeout (4000ms), maintaining high responsiveness.

**Known Limitation:** All Cobalt instances are public and may go offline without notice. When all 9 instances are unreachable, audio downloads fail with a 500 error. A local `yt-dlp` fallback is **planned** but not yet implemented.

---

## 🎛️ Processing Options (Audio Filters)

When harvesting a segment, users can enable optional audio processing filters applied via FFmpeg's `-af` flag:

| Option | Filter | Description | Status |
|--------|--------|-------------|--------|
| `normalization` | `loudnorm=I=-14:TP=-1:LRA=11` | EBU R128 loudness normalization targeting -14 LUFS | ✅ Functional |
| `fadeInOut` | `afade=t=in:st=0:d=0.05,afade=t=out:st=<end-0.05>:d=0.05` | 50ms linear fade-in/out to prevent boundary clicks | ✅ Functional |
| `voiceIsolation` | Demucs neural voice separation | Isolate vocals from background audio | 🔜 Coming Soon |
| `silenceTrimming` | WhisperX silence detection | Trim leading/trailing silence from clips | 🔜 Coming Soon |

When no options are enabled, the harvest produces a raw FFmpeg slice with no filters applied.

---

## 💾 JSON Database Schema

The local persistent database is saved in `vocal_harvester_db.json`. It is structured as an object with two normalized arrays: `samples` and `tags`.

```json
{
  "samples": [
    {
      "id": "samp_shouting_intro",
      "phrase_text": "Your time is limited, so don't waste it living someone else's life.",
      "video_id": "UF8uR6Z6KLc",
      "video_title": "Steve Jobs Stanford Commencement Address",
      "start_time": 543.0,
      "duration": 5.5,
      "file_path": "/api/samples/audio/samp_shouting_intro",
      "energy_score": 0.78,
      "is_processed": true,
      "createdAt": "2026-06-28T13:30:00.000Z"
    }
  ],
  "tags": [
    { "id": "tag_1", "sample_id": "samp_shouting_intro", "category": "emotion", "value": "inspired" },
    { "id": "tag_2", "sample_id": "samp_shouting_intro", "category": "gender", "value": "masculine" },
    { "id": "tag_3", "sample_id": "samp_shouting_intro", "category": "role", "value": "orator" }
  ]
}
```

### Schema Notes

- **`samples`** is an array of sample objects. Each sample has a unique `id` prefixed with `samp_`.
- **`tags`** is a normalized array of tag objects. Each tag references a `sample_id` and has a `category`/`value` pair.
- Tags are stored separately (not embedded in samples) to allow efficient tag-based filtering across the library.
- The database file is parsed synchronously during server initialization and saved to disk whenever entries are created, updated, or deleted.
- Field naming uses `snake_case` throughout: `phrase_text`, `video_id`, `video_title`, `start_time`, `file_path`, `energy_score`, `is_processed`, `sample_id`.
