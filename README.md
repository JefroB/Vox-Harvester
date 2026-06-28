# YouTube Vocal Harvester

A full-stack web application for searching YouTube videos, extracting spoken phrases with millisecond accuracy, and harvesting high-quality audio samples for speech synthesis training, vocal sampling, and speech archiving.

## Quick Start

```bash
# Install dependencies
npm install

# Start the development server
npm run dev
```

The app runs at [http://localhost:3000](http://localhost:3000).

## How It Works

1. **Search** — Enter a query to find YouTube videos with vocal content
2. **Align** — Browse auto-grouped transcript phrases with precise timestamps
3. **Preview** — Listen to sample-accurate audio slices with waveform visualization
4. **Harvest** — Save cropped WAV samples to your local library with metadata tags

## Tech Stack

- **Frontend:** React 19, Vite, Tailwind CSS, canvas waveform visualizer
- **Backend:** Node.js, Express, TypeScript (`tsx`)
- **Database:** JSON-based local store (`vocal_harvester_db.json`)
- **Audio:** FFmpeg (sample-accurate slicing), Cobalt + yt-dlp download
- **AI:** Google Gemini for search grounding and transcript fallbacks

## Documentation

Full developer handbook, architecture, and API reference live in [`docs/`](./docs/README.md):

- [Developer & LLM Handbook](./docs/README.md) — Master guide and index
- [Architecture](./docs/ARCHITECTURE.md) — System design and component relationships
- [Audio Alignment & Slicing](./docs/ALIGNMENT_AND_SLICING.md) — FFmpeg strategy and precision details
- [API Reference](./docs/API_REFERENCE.md) — Full endpoint documentation

## Development

```bash
# Run tests
.venv/bin/python -m pytest tests/ --no-header -q

# Run with coverage
.venv/bin/python -m pytest tests/ --cov=src/codesearch --cov-report=term-missing
```

## License

Private — all rights reserved.
