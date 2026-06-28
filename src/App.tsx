import React, { useState } from "react";
import { 
  Flame, Scissors, Sparkles, Youtube, CheckSquare, Music, Shield, Info, Keyboard, Disc 
} from "lucide-react";
import YoutubeSearch from "./components/YoutubeSearch";
import TranscriptAligner from "./components/TranscriptAligner";
import ActiveJobs from "./components/ActiveJobs";
import Library from "./components/Library";
import AcousticMonitor from "./components/AcousticMonitor";
import { VideoMeta } from "./types";

interface ActivePreview {
  videoId: string;
  startTime: number;
  endTime: number;
  phraseText: string;
  sourceTitle: string;
}

export default function App() {
  const [selectedVideo, setSelectedVideo] = useState<VideoMeta | null>(null);
  
  // Track active jobs submitted through alignment step
  const [activeJobIds, setActiveJobIds] = useState<string[]>([]);
  // Triggers updates on Library list
  const [libraryRefreshTrigger, setLibraryRefreshTrigger] = useState<number>(0);

  // Global clip playback audio preview monitor state
  const [activePreview, setActivePreview] = useState<ActivePreview | null>(null);

  const handleSelectVideo = (video: VideoMeta) => {
    setSelectedVideo(video);
  };

  const handleHarvestStarted = (jobId: string) => {
    setActiveJobIds(prev => [jobId, ...prev]);
  };

  const handleJobCompleted = (sampleId: string) => {
    // Notify library to query refreshed samples database
    setLibraryRefreshTrigger(prev => prev + 1);
  };

  const handleJobRemoved = (jobId: string) => {
    setActiveJobIds(prev => prev.filter(id => id !== jobId));
  };

  /**
   * Handles preview clip playback initiation or stop requests from the Library component.
   *
   * When `videoId` is empty (stop signal from Library's `handleTogglePlay`), sets `activePreview`
   * to `null` which unmounts AcousticMonitor cleanly without triggering an API request with
   * invalid empty parameters. When `videoId` is non-empty, sets `activePreview` to the clip
   * metadata object which mounts AcousticMonitor with valid streaming params.
   *
   * @param videoId - YouTube video ID; empty string signals playback stop
   * @param startTime - Clip start time in seconds
   * @param endTime - Clip end time in seconds
   * @param phraseText - Transcript phrase for display
   * @param sourceTitle - Video title for attribution
   */
  const handlePreviewClip = (videoId: string, startTime: number, endTime: number, phraseText: string, sourceTitle: string) => {
    // why guard: Library calls onPreviewClip("", 0, 0, "", "") to stop playback.
    // Without this guard, AcousticMonitor would mount with empty videoId and fire
    // a broken /api/audio-stream?videoId=&start=0&end=0 request → 400 error.
    if (!videoId) {
      setActivePreview(null);
    } else {
      setActivePreview({ videoId, startTime, endTime, phraseText, sourceTitle });
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-cyan-500 selection:text-slate-950 flex flex-col font-sans" id="vocal-harvester-app">
      {/* Premium Top Navigation Header */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-tr from-cyan-600 to-emerald-500 p-2 rounded-lg shadow-inner ring-1 ring-white/10">
            <Disc className="w-5 h-5 text-slate-950 animate-[spin_4s_linear_infinite]" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              YouTube Vocal Harvester
              <span className="text-[10px] bg-cyan-950/80 text-cyan-400 border border-cyan-800 px-1.5 py-0.2 rounded font-mono lowercase tracking-normal">
                v1.2 mvp
              </span>
            </h1>
            <p className="text-xs text-slate-400 hidden sm:block">Analyze transcript alignments and isolate pristine vocal samples for samplers &amp; DAWs</p>
          </div>
        </div>

        {/* Integration Credentials Info */}
        <div className="flex items-center gap-3">
          <span className="text-[10.5px] font-mono text-slate-400 bg-slate-900/60 px-3 py-1.5 rounded-lg border border-slate-800 hidden md:flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-cyan-400" />
            <span>AI Studio Server Active</span>
          </span>
        </div>
      </header>

      {/* Main Container Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        
        {/* Architectural Overview Card explaining the pipeline */}
        <section className="bg-slate-900/40 border border-slate-900 rounded-xl p-5" id="system-vision-banner">
          <div className="flex items-start gap-4">
            <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-cyan-400 hidden sm:block">
              <Sparkles className="w-5 h-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-slate-200">Production-Ready Vocal Acquisition Pipeline</h2>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                The Vocal Harvester implements high-quality voice separation logic mapped directly into sample banks. 
                Search target videos with human-generated Closed Captions filtering parameter <code className="bg-slate-950 text-cyan-400 px-1 rounded">&amp;sp=EgQQASgB</code>, 
                retrieve precise SRT timestamps via fast-path VTT downloads, fine-tune bounds with sub-second precision, and process audio through 
                the <strong className="text-slate-300">Demucs</strong> voice-isolation and normalization stage.
              </p>
            </div>
          </div>
        </section>

        {/* Acquisition & Alignment Side-by-Side Panels */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 h-full">
            <YoutubeSearch 
              onSelectVideo={handleSelectVideo} 
              selectedVideoId={selectedVideo?.id || null} 
            />
          </div>

          <div className="lg:col-span-7 h-full">
            <TranscriptAligner 
              video={selectedVideo} 
              onHarvestStarted={handleHarvestStarted} 
              onPreviewClip={handlePreviewClip}
            />
          </div>
        </section>

        {/* Active background tasks tracking queue */}
        <ActiveJobs 
          jobIds={activeJobIds} 
          onJobCompleted={handleJobCompleted} 
          onJobRemoved={handleJobRemoved} 
        />

        {/* Mapped Samples Library Explorer */}
        <Library 
          refreshTrigger={libraryRefreshTrigger} 
          onPreviewClip={handlePreviewClip}
          activePreviewId={activePreview ? `${activePreview.videoId}-${activePreview.startTime}` : null}
        />

        {/* Keyboard and DAW usage helper shortcuts bottom bento block */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4" id="producer-tips-section">
          <div className="bg-slate-900/30 border border-slate-900 p-4 rounded-xl flex items-start gap-3">
            <Keyboard className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-semibold text-slate-300 font-mono">1. SAMPLE PREVIEW CONTROLS</h4>
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">Click on any sample's waveform bar inside the library page to immediate play/pause custom synthesized vocal stabs.</p>
            </div>
          </div>

          <div className="bg-slate-900/30 border border-slate-900 p-4 rounded-xl flex items-start gap-3">
            <Flame className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-semibold text-slate-300 font-mono">2. ENERGY EQUALIZATION SHAPING</h4>
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">Energy scores reflect vowel prominence and speech intensity, assisting sequencing on gear like Polyend or Korg.</p>
            </div>
          </div>

          <div className="bg-slate-900/30 border border-slate-900 p-4 rounded-xl flex items-start gap-3">
            <CheckSquare className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-semibold text-slate-300 font-mono">3. DIRECT DRAG &amp; DROP WAV EXPORTS</h4>
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">Download files to instantly append pristine 44.1kHz WAV sequences directly inside Logic Pro, Ableton Live, or FL Studio.</p>
            </div>
          </div>
        </section>
      </main>

      {/* Floating Acoustic Studio Monitor Widget overlay */}
      {activePreview && (
        <AcousticMonitor
          videoId={activePreview.videoId}
          startTime={activePreview.startTime}
          endTime={activePreview.endTime}
          phraseText={activePreview.phraseText}
          sourceTitle={activePreview.sourceTitle}
          onClose={() => setActivePreview(null)}
        />
      )}

      {/* Humble Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-600 font-mono">
        <p>© 2026 YouTube Vocal Harvester. High-Fidelity Audio Demucs &amp; WhisperX Pipeline Architecture.</p>
      </footer>
    </div>
  );
}