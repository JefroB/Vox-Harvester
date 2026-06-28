# Full-Stack API Reference

This document catalogs all backend Express REST API routes, parameter expectations, request payloads, and response JSON formats for the YouTube Vocal Harvester.

---

## 1. Video Discovery & Transcripts

### 🔍 Search YouTube Videos
Queries YouTube to discover video candidates for vocal harvesting.

* **URL:** `/api/search`
* **Method:** `POST`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "query": "Schwarzenegger motivation"
}
```
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "results": [
    {
      "id": "u0b8_g_dQw4",
      "title": "Arnold Schwarzenegger Ultimate Motivation",
      "channelName": "Motivator Channel",
      "duration": "10:15",
      "description": "Arnold discusses the importance of hard work and self-belief.",
      "thumbnailUrl": "https://img.youtube.com/vi/u0b8_g_dQw4/mqdefault.jpg"
    }
  ]
}
```

---

### 📜 Retrieve Video Transcript
Fetches subtitles/captions for a target YouTube video ID, grouping raw cues into logical sentence phrases.

* **URL:** `/api/transcripts`
* **Method:** `POST`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "videoId": "u0b8_g_dQw4",
  "videoTitle": "Arnold Schwarzenegger Ultimate Motivation"
}
```
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "phrases": [
    {
      "id": "scrape_u0b8_g_dQw4_1",
      "start": 12.4,
      "end": 17.8,
      "text": "The mind is the limit. As long as the mind can envision the fact...",
      "speaker": "Speaker",
      "confidence": 0.99,
      "tags": [
        { "id": "tag_emotion_default", "category": "emotion", "value": "natural" },
        { "id": "tag_gender_default", "category": "gender", "value": "neutral" },
        { "id": "tag_role_default", "category": "role", "value": "orator" }
      ]
    }
  ]
}
```

---

## 2. Audio Preview & Harvesting

### 🎵 Preview Audio Stream
Generates and streams an accurate, live-sliced audio preview for a given segment and customized offsets.

* **URL:** `/api/audio-stream`
* **Method:** `GET`
* **Query Parameters:**
  * `videoId` (string, required) – Target YouTube video ID.
  * `start` (number, required) – Start timestamp in seconds.
  * `end` (number, required) – End timestamp in seconds.
* **Response Status:** `200 OK`
* **Response Headers:**
  * `Content-Type: audio/wav`
* **Response Content:** Binary WAV audio stream.

---

### 🌾 Harvest Vocal Segment
Initiates a background job to download the master stream, slice the target segment, and log it to the database library.

* **URL:** `/api/harvest`
* **Method:** `POST`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "videoId": "u0b8_g_dQw4",
  "videoTitle": "Arnold Schwarzenegger Ultimate Motivation",
  "phraseText": "The mind is the limit. As long as the mind can envision...",
  "startTime": 12.4,
  "endTime": 17.8,
  "options": {
    "voiceIsolation": false,
    "silenceTrimming": false,
    "normalization": true,
    "fadeInOut": true
  }
}
```

**Note on Processing Options:**
- `normalization`: When true, applies FFmpeg `loudnorm` filter (EBU R128, -14 LUFS).
- `fadeInOut`: When true, applies 50ms linear fade-in at start and 50ms fade-out at end.
- `voiceIsolation`: Demucs voice isolation — **coming soon** (currently non-functional).
- `silenceTrimming`: WhisperX silence trimming — **coming soon** (currently non-functional).

* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "jobId": "job_1718290342930"
}
```

---

### ⏱️ Check Harvest Job Status
Checks progress or logs failures for a background harvest process.

* **URL:** `/api/jobs/:id`
* **Method:** `GET`
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "id": "job_1718290342930",
  "video_id": "u0b8_g_dQw4",
  "video_title": "Arnold Schwarzenegger Ultimate Motivation",
  "phrase_text": "The mind is the limit...",
  "start_time": 12.4,
  "end_time": 17.8,
  "status": "completed",
  "progress": 100,
  "message": "Successfully separated and stored authentic vocal sample!",
  "options": {
    "voiceIsolation": false,
    "silenceTrimming": false,
    "normalization": true,
    "fadeInOut": true
  },
  "createdAt": "2026-06-28T13:30:00.000Z",
  "resultSampleId": "samp_abc123def"
}
```

Job `status` can be: `"pending"` | `"processing"` | `"completed"` | `"failed"`.

---

## 3. Sample Library Management

### 📚 Retrieve All Harvested Samples
Returns the catalog of all successfully processed vocal clips with associated tags.

* **URL:** `/api/samples`
* **Method:** `GET`
* **Query Parameters (optional):**
  * `q` (string) – Text search filter across phrase text and video title.
  * `category` (string) – Filter by tag category (e.g., "emotion", "gender").
  * `value` (string) – Filter by tag value within the specified category.
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "samples": [
    {
      "id": "samp_abc123def",
      "phrase_text": "The mind is the limit...",
      "video_id": "u0b8_g_dQw4",
      "video_title": "Arnold Schwarzenegger Ultimate Motivation",
      "start_time": 12.4,
      "duration": 5.4,
      "file_path": "/api/samples/audio/samp_abc123def",
      "energy_score": 0.78,
      "is_processed": true,
      "createdAt": "2026-06-28T13:30:10.000Z",
      "tags": [
        { "id": "t_samp_abc123def_1", "sample_id": "samp_abc123def", "category": "emotion", "value": "motivated" },
        { "id": "t_samp_abc123def_2", "sample_id": "samp_abc123def", "category": "gender", "value": "masculine" }
      ]
    }
  ],
  "allTags": [
    { "id": "t_samp_abc123def_1", "sample_id": "samp_abc123def", "category": "emotion", "value": "motivated" }
  ],
  "tagFacets": {
    "emotion": ["excited", "calm", "motivated", "focused", "creative"],
    "gender": ["masculine", "feminine"],
    "role": ["vocals", "orator", "narrator"]
  }
}
```

---

### 🗑️ Delete a Sample
Deletes a harvested sample from the local file system and database catalog.

* **URL:** `/api/samples/:id`
* **Method:** `DELETE`
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "success": true,
  "message": "Sample deleted successfully"
}
```

---

### ➕ Add Custom Tag to a Sample
Associates a new metadata categorization tag to a target library clip.

* **URL:** `/api/samples/:id/tags`
* **Method:** `POST`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
```json
{
  "category": "gender",
  "value": "masculine"
}
```
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "success": true,
  "tag": {
    "id": "tag_1718290382901",
    "sample_id": "samp_abc123def",
    "category": "gender",
    "value": "masculine"
  }
}
```

---

### ➖ Remove a Tag from a Sample
Disassociates an active metadata tag from a target library clip.

* **URL:** `/api/samples/:id/tags/:tagId`
* **Method:** `DELETE`
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "success": true
}
```

---

### 📈 Retrieve Sample Waveform Peaks
Fetches the pre-calculated list of 80 sound pressure levels for drawing canvas graphics.

* **URL:** `/api/samples/peaks/:id`
* **Method:** `GET`
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "id": "samp_abc123def",
  "peaks": [0.04, 0.23, 0.81, 0.92, 0.45, 0.08, 0.04]
}
```

The `peaks` array contains exactly 80 normalized floats (0.0–1.0), with a minimum floor of 0.04 for visual rendering.

---

### 🔊 Retrieve Sliced WAV Binary File
Serves the raw high-fidelity WAV file of a harvested library sample.

* **URL:** `/api/samples/audio/:id`
* **Method:** `GET`
* **Response Status:** `200 OK`
* **Response Headers:**
  * `Content-Type: audio/wav`
* **Response Content:** Binary WAV audio file (mono, 16-bit, 44.1kHz PCM).
