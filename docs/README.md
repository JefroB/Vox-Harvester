# YouTube Vocal Harvester: Developer & LLM Handbook

Welcome to the **YouTube Vocal Harvester** project repository. This document serves as the master guide and entry point for developers, system architects, or subsequent LLMs taking over development or maintenance of this application.

## 📋 Table of Contents
1. [System Architecture Overview](./ARCHITECTURE.md)
2. [Audio Alignment & Precise FFmpeg Slicing](./ALIGNMENT_AND_SLICING.md)
3. [Full-Stack API Reference](./API_REFERENCE.md)

---

## 🚀 Application Objective

The **YouTube Vocal Harvester** is a high-performance, full-stack web application designed to allow users to search for YouTube videos, extract spoken phrases with millisecond accuracy, preview aligned vocal segments, and crop/save high-quality audio samples (`.wav` format) into a local database and file storage system. 

It is tailored for speech synthesis training dataset creation, vocal sampling for music production, and precise speech snippet archiving.

### Main User Flow
1. **Step 1: Search & Video Discovery** – Users enter a query (e.g., searching for speeches, interviews, or lectures) and select a video.
2. **Step 2: Transcript Alignment & Selection** – The system retrieves and parses subtitles/captions, automatically grouping raw cues into natural sentence phrases. Users select a phrase, customize start/end offsets, enable processing options (normalization, fades), and preview the live-sliced audio block.
3. **Step 3: Acoustic Waveform Visualization** – The system renders an interactive acoustic waveform display where users can analyze peak structures, listen with precise scrub controls, and configure metadata tags (e.g., emotion, gender, speaker name).
4. **Step 4: Sample Harvesting & Library Management** – Users batch-harvest or individually save the sliced audio clips. The samples are cataloged in a local database, permitting custom tag modification, file downloads, and library cleanup.

---

## 🛠️ Key Challenges Resolved (Historical Backlog)

During development, two major bugs affected the system's core capabilities. Understanding these resolutions is critical to preserving system stability:

### 1. Inaccurate/Mismatched Transcripts in Step 2
* **The Bug:** Selecting different videos often yielded identical transcripts, or retrieved captions that had zero relevance to the video context or search query. 
* **The Root Cause:** The server-side scraper relied on direct parsing of the YouTube watch HTML page's regex context, which is highly prone to rate limits, geographical blocks, and HTML structure modifications. This often caused the scraper to fall back on generic/stale cached transcripts or fail silently.
* **The Resolution:** 
  * We integrated the dedicated `youtube-transcript` npm library as the high-priority transcript retrieval channel on the backend.
  * It communicates directly with internal YouTube caption endpoints, returning robust, accurate timed cues.
  * We retained the direct HTML scraper solely as an isolated secondary fallback layer.
  * In addition, we implemented an **intelligent cue grouping algorithm** on the backend. Instead of displaying tiny 1-3 word snippets, raw cues are combined into natural phrases (max duration: 6.5s, max inter-cue gap: 1.8s, max word count: 10), preserving human conversational flow.

### 2. Audio Preview Displacement & Misalignment (Wrong Audio Snippets)
* **The Bug:** When previewing a selected caption in Step 2, the audio segment played would be offset by several seconds, often playing the wrong spoken quote or capturing adjacent sentences.
* **The Root Cause (The FFmpeg Seeking Trap):** 
  * The backend utilizes **Cobalt parallel scraping** to download high-quality YouTube audio as a master MP3 (`.mp3`).
  * Slicing was originally implemented with the FFmpeg command layout:
    `ffmpeg -y -ss {startTime} -t {duration} -i {input_mp3} ...`
  * Placing the seek parameter (`-ss`) **before** the input flag (`-i`) instructs FFmpeg to perform a *fast seek* at the container level. In compressed audio formats (such as MP3), this jumps to the nearest keyframe or frame boundary without decoding. While ultra-fast, this is **not sample-accurate** and resulted in preview discrepancies of up to 3–5 seconds on long files.
* **The Resolution:**
  * We shifted the seek command to a **sample-accurate, decoding-based seek** structure:
    `ffmpeg -y -i {input_mp3} -ss {startTime} -t {duration} ...`
  * Placing `-ss` **after** `-i` forces FFmpeg to decode the compressed stream from the beginning up to the target start point. While slightly more CPU-heavy, it yields **microsecond-precise alignment**, guaranteeing the played audio perfectly matches the selected words.
  * To prevent stale previews, the server was configured to clear any cached sliced WAV chunks on startup.

---

## 🏗️ Technology Stack

* **Frontend:** React 19 (Vite-driven SPA), Tailwind CSS for high-performance styling, `lucide-react` icons, custom canvas-based waveform visualizer.
* **Backend:** Node.js, Express, TypeScript runtime (`tsx` in development).
* **Database:** JSON-based local store (`vocal_harvester_db.json`) with normalized `samples` and `tags` arrays.
* **AI Integration:** Google Gemini (via `@google/genai` SDK) for search grounding and transcript generation fallbacks.
* **Utilities:** `ffmpeg` (via `ffmpeg-static` binaries) for ultra-accurate segment processing.

---

## ⚠️ Known Limitations & Planned Features

| Feature | Status | Notes |
|---------|--------|-------|
| Cobalt parallel download | ✅ Active | Primary audio source; depends on 9 public instances |
| Local yt-dlp fallback | ✅ Active | Secondary fallback when all Cobalt instances are down |
| Demucs voice isolation | 🔜 Planned | Neural voice separation from background audio |
| WhisperX silence trimming | 🔜 Planned | Automatic leading/trailing silence removal |
| FFmpeg loudnorm | ✅ Active | EBU R128 normalization filter |
| FFmpeg fade in/out | ✅ Active | 50ms boundary fade filters |
