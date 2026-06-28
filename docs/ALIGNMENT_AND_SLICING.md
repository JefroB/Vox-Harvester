# Transcript Alignment & Precise Audio Slicing

This document outlines the mechanics of YouTube caption retrieval, intelligent phrase grouping, sample-accurate FFmpeg seeking, and the acoustic wave processing algorithms that power the application.

---

## 🗣️ Transcript Retrieval & Cue Grouping

Raw captions retrieved from YouTube are typically divided into extremely small timed cues (e.g., 1–3 words, lasting under a second) to fit on-screen video presentation. These brief cues are poorly suited for vocal databases or speech analysis because they isolate words from their conversational context.

To solve this, the backend implements an **Intelligent Aggregation Algorithm** within the `groupCuesIntoPhrases` function:

```typescript
function groupCuesIntoPhrases(videoId: string, rawCues: any[]): any[] {
  const phraseSegments: any[] = [];
  let currentText = "";
  let phraseStart = -1;
  let phraseEnd = -1;
  let wordCount = 0;
  
  for (let i = 0; i < rawCues.length; i++) {
    const cue = rawCues[i];
    const cueWordCount = cue.text.split(/\s+/).filter(Boolean).length;
    
    if (phraseStart === -1) {
      phraseStart = cue.start;
      currentText = cue.text;
      phraseEnd = cue.end;
      wordCount = cueWordCount;
    } else {
      const currentDuration = cue.end - phraseStart;
      const gap = cue.start - phraseEnd;
      
      // GROUPING CONSTRAINTS:
      // 1. Total words in the phrase must not exceed 10.
      // 2. Continuous phrase duration must remain under 6.5 seconds.
      // 3. Gap between the end of the last cue and start of the next must be under 1.8 seconds.
      if (wordCount + cueWordCount <= 10 && currentDuration < 6.5 && gap < 1.8) {
        currentText += " " + cue.text;
        phraseEnd = cue.end;
        wordCount += cueWordCount;
      } else {
        // Close the current phrase and push to segments list
        phraseSegments.push({
          id: `scrape_${videoId}_${phraseSegments.length + 1}`,
          start: Number(phraseStart.toFixed(2)),
          end: Number(phraseEnd.toFixed(2)),
          text: currentText,
          speaker: "Speaker",
          confidence: 0.99,
          tags: [...]
        });
        
        // Begin a new phrase segment
        phraseStart = cue.start;
        currentText = cue.text;
        phraseEnd = cue.end;
        wordCount = cueWordCount;
      }
    }
  }
  // (Remaining trail-end cue handling and filtering out too-short samples)
}
```

### Key Thresholds
* **Length Guard:** Output phrases must be at least **1.0 second** long and contain a minimum of **8 characters** (trimmed) to prevent capturing random breaths, filler words, or static noise.
* **Volume Cap:** It restricts the results to a maximum of the **first 15 aggregated sentences** per video, maintaining high responsiveness and clean UI presentation.

---

## 🎯 Sample-Accurate FFmpeg Seeking

Audio alignment errors occur when FFmpeg's parameters are structured sub-optimally. The location of the seek parameter (`-ss`) relative to the input file flag (`-i`) alters how the binary processes compressed audio files (like MP3):

### ❌ Inaccurate Seeking (Fast Seek)
```bash
ffmpeg -y -ss 45.5 -t 5.0 -i input_master.mp3 output_trimmed.wav
```
* **How it works:** Placing `-ss` **before** `-i` instructs FFmpeg to skip directly to the container's frame header offset corresponding to roughly 45.5 seconds.
* **The Problem:** It does not decode preceding frames. Because MP3 uses inter-frame compression, the decoder must align to the nearest keyframe block. The resulting audio can be off by **3 to 5 seconds**, resulting in chopped audio, silence, or wrong voices.

### ✅ Sample-Accurate Seeking (Safe Seek)
```bash
ffmpeg -y -i input_master.mp3 -ss 45.5 -t 5.0 -acodec pcm_s16le -ac 1 -ar 44100 output_trimmed.wav
```
* **How it works:** Placing `-ss` **after** `-i` tells FFmpeg to open and actively decode the input stream *from the very beginning*, discarding decoded samples until it reaches precisely 45.5 seconds, then extracting exactly 5.0 seconds.
* **The Benefit:** It guarantees **sample-accurate seeking** to the exact millisecond, even on highly compressed MP3 media.
* **Audio Format:** The sliced segment is compiled into a CD-quality **Mono, 16-bit, 44.1kHz PCM WAV** track (`-acodec pcm_s16le -ac 1 -ar 44100`), which is ideal for acoustic analysis, speech recognition, and waveform rendering.

### 🎛️ Optional Audio Filter Chain

When processing options are enabled during harvest, the FFmpeg command includes an `-af` filter argument:

```bash
# With normalization + fade enabled:
ffmpeg -y -i input_master.mp3 -ss 45.5 -t 5.0 -af "loudnorm=I=-14:TP=-1:LRA=11,afade=t=in:st=0:d=0.05,afade=t=out:st=4.95:d=0.05" -acodec pcm_s16le -ac 1 -ar 44100 output.wav
```

| Filter | Purpose |
|--------|---------|
| `loudnorm=I=-14:TP=-1:LRA=11` | EBU R128 loudness normalization |
| `afade=t=in:st=0:d=0.05` | 50ms linear fade-in at start |
| `afade=t=out:st=<end-0.05>:d=0.05` | 50ms linear fade-out at end |

When no processing options are enabled, no `-af` flag is included and the output is a raw unprocessed slice.

---

## 📊 Peak Data Generation Algorithm (`generatePeakData`)

To render a fast, lightweight waveform visualizer in the React frontend without downloading multi-megabyte audio files over the network, the server parses the raw PCM bytes of the generated WAV and downsamples it into an array of exactly **80 peak amplitudes**.

### Raw WAV Analysis
A WAV file consists of a 44-byte header followed by raw PCM data. For a 16-bit mono WAV, each audio sample is a 2-byte (16-bit) signed little-endian integer (`Int16LE`).

```typescript
function generatePeakData(audioBuffer: Buffer): number[] {
  const rawDataOffset = 44; // Skip the standard 44-byte RIFF WAV header
  const numInt16Samples = (audioBuffer.length - rawDataOffset) / 2;
  const numPeaks = 80;
  const samplesPerChunk = Math.floor(numInt16Samples / numPeaks);
  const peaks: number[] = [];

  for (let i = 0; i < numPeaks; i++) {
    let maxAmp = 0;
    const startSample = i * samplesPerChunk;
    const endSample = Math.min((i + 1) * samplesPerChunk, numInt16Samples);

    for (let s = startSample; s < endSample; s++) {
      // Read 2-byte signed Int16LE sample
      const val = Math.abs(audioBuffer.readInt16LE(rawDataOffset + s * 2));
      if (val > maxAmp) {
        maxAmp = val;
      }
    }
    // Normalize to 0.0 - 1.0 based on maximum Int16 amplitude (32768)
    const peakNormalized = Number((maxAmp / 32768).toFixed(3));
    
    // Ensure a minimum visual height of 0.04 so silent portions don't disappear in UI
    peaks.push(Math.max(0.04, peakNormalized));
  }
  return peaks;
}
```

The frontend client fetches these 80 numeric points from `/api/samples/peaks/:id` and draws them on an HTML5 `<canvas>` using vertical columns mirrored on a center line, producing a professional, fully interactive waveform display.
