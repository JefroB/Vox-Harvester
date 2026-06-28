import React, { useState, useEffect } from "react";
import { 
  FileText, Scissors, Sliders, Play, Settings, Sparkles, Loader2, Info, ChevronRight
} from "lucide-react";
import { VideoMeta, SpokenPhrase, ProcessingOptions } from "../types";

interface TranscriptAlignerProps {
  video: VideoMeta | null;
  onHarvestStarted: (jobId: string) => void;
  onPreviewClip?: (videoId: string, startTime: number, endTime: number, phraseText: string, sourceTitle: string) => void;
}

export default function TranscriptAligner({ video, onHarvestStarted, onPreviewClip }: TranscriptAlignerProps) {
  const [phrases, setPhrases] = useState<SpokenPhrase[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedPhrase, setSelectedPhrase] = useState<SpokenPhrase | null>(null);

  // Manual trimming adjustments (Start/End slider bounds)
  const [trimStart, setTrimStart] = useState<number>(0);
  const [trimEnd, setTrimEnd] = useState<number>(0);
  const [phraseTimelinePoints, setPhraseTimelinePoints] = useState<{ start: number; end: number }>({ start: 0, end: 0 });

  // DSP & AI plugins checkboxes
  const [options, setOptions] = useState<ProcessingOptions>({
    voiceIsolation: false, // Demucs
    silenceTrimming: false, // Trim silence
    normalization: true, // FFmpeg Loudnorm (-14 LUFStr)
    fadeInOut: true // dual 0.05s linear/cos fade-ins to prevent boundary clicks
  });

  const [isHarvesting, setIsHarvesting] = useState(false);
  const [extractionPathType, setExtractionPathType] = useState<'fast' | 'slow'>('fast');

  // Trigger transcript load on selected video modification
  useEffect(() => {
    if (!video) return;

    const fetchTranscripts = async () => {
      setIsLoading(true);
      setSelectedPhrase(null);
      try {
        const res = await fetch("/api/transcripts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ videoId: video.id, videoTitle: video.title })
        });
        const data = await res.json();
        setPhrases(data.phrases || []);
        
        // Auto-select first phrase for convenience
        if (data.phrases && data.phrases.length > 0) {
          handleSelectPhrase(data.phrases[0]);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setIsLoading(false);
      }
    };

    fetchTranscripts();
  }, [video]);

  const handleSelectPhrase = (phrase: SpokenPhrase) => {
    setSelectedPhrase(phrase);
    setPhraseTimelinePoints({ start: phrase.start, end: phrase.end });
    setTrimStart(phrase.start);
    setTrimEnd(phrase.end);

    // Randomize path types just to showcase different spec workflows (WhisperX vs direct pull)
    setExtractionPathType(phrase.confidence > 0.95 ? 'fast' : 'slow');
  };

  const handleHarvest = async () => {
    if (!video || !selectedPhrase) return;

    setIsHarvesting(true);
    try {
      const res = await fetch("/api/harvest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videoId: video.id,
          videoTitle: video.title,
          phraseText: selectedPhrase.text,
          startTime: trimStart,
          endTime: trimEnd,
          options
        })
      });
      const data = await res.json();
      if (data.jobId) {
        onHarvestStarted(data.jobId);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsHarvesting(false);
    }
  };

  // Safe manual adjustments
  const handleStartShift = (val: number) => {
    if (val < trimEnd - 0.2) {
      setTrimStart(Number(val.toFixed(2)));
    }
  };

  const handleEndShift = (val: number) => {
    if (val > trimStart + 0.2) {
      setTrimEnd(Number(val.toFixed(2)));
    }
  };

  const currentDuration = Math.max(0, Number((trimEnd - trimStart).toFixed(2)));

  if (!video) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-center h-[340px]" id="no-video-loaded">
        <FileText className="w-10 h-10 text-slate-700 mb-3" />
        <h3 className="text-slate-400 font-medium text-sm">No Active Video Segment Sourced</h3>
        <p className="text-xs text-slate-500 max-w-xs mt-1.5">
          Select or search a video source from step 1 to analyze captions and alignment timestamps.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl" id="transcript-aligner-container">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-cyan-500" />
          <h2 className="text-lg font-medium text-slate-100 tracking-tight">2. Caption Retrieval &amp; Alignment</h2>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-400 font-medium bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 truncate max-w-[200px]">
            {video.title}
          </span>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-12 text-center" id="aligner-loader">
          <Loader2 className="w-8 h-8 text-cyan-500 animate-spin mb-3" />
          <p className="text-xs text-slate-400 font-mono">RETRIEVING SOURCE CAPTION STRUCTS...</p>
          <span className="text-[10px] text-slate-500 mt-1 max-w-xs">Polling WhisperX aligner and mapping SRT structures</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Phrases List */}
          <div className="lg:col-span-6 space-y-2">
            <div className="text-xs font-mono text-slate-500 flex items-center justify-between px-1">
              <span>SPOKEN SEGMENTS IDENTIFIED ({phrases.length})</span>
              <span>CONFIDENCE / PATH</span>
            </div>

            <div className="space-y-2 max-h-[310px] overflow-y-auto pr-1 custom-scrollbar" id="phrases-scroller">
              {phrases.map((phrase) => {
                const isSelected = selectedPhrase?.id === phrase.id;
                return (
                  <div
                    key={phrase.id}
                    onClick={() => handleSelectPhrase(phrase)}
                    className={`p-3 rounded-lg border text-left cursor-pointer transition-all ${
                      isSelected
                        ? "bg-cyan-950/40 border-cyan-500/80"
                        : "bg-slate-950 border-slate-800/80 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex justify-between items-center text-[10px] font-mono text-slate-500 mb-1.5">
                      <span className="text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                        {phrase.speaker || "Speaker"} • {phrase.start}s - {phrase.end}s
                      </span>
                      <div className="flex items-center gap-2">
                        <span className={phrase.confidence > 0.95 ? 'text-emerald-500 font-semibold' : 'text-yellow-500'}>
                          {(phrase.confidence * 100).toFixed(0)}%
                        </span>
                        <span className={`text-[8px] font-bold px-1.5 py-0.2 rounded uppercase ${
                          phrase.confidence > 0.95 
                            ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900' 
                            : 'bg-yellow-950/50 text-yellow-400 border border-yellow-900'
                        }`}>
                          {phrase.confidence > 0.95 ? 'vtt fast' : 'whisperx'}
                        </span>
                      </div>
                    </div>
                    
                    <p className="text-xs text-slate-200 font-medium leading-relaxed" id={`phrase-text-${phrase.id}`}>
                      "{phrase.text}"
                    </p>

                    <div className="flex flex-wrap gap-1 mt-2">
                      {phrase.tags?.map((t, idx) => (
                        <span key={idx} className="text-[8.5px] font-mono bg-slate-900 text-slate-400 border border-slate-800/80 px-1.5 py-0.2 rounded-sm lowercase">
                          {t.category}:{t.value}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Manual Alignment & Trimming Details */}
          <div className="lg:col-span-6 bg-slate-950/40 border border-slate-800 rounded-lg p-4 flex flex-col justify-between">
            {selectedPhrase ? (
              <div className="space-y-5">
                
                {/* Header overview */}
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                    <Scissors className="w-3.5 h-3.5 text-cyan-500" />
                    Fine-Tuning Manual Alignment
                  </span>
                  
                  <div className="flex items-center gap-1.5 text-[9px] font-mono">
                    <span className="text-slate-500">PATH:</span>
                    <span className={`px-1.5 py-0.2 rounded uppercase font-bold ${
                      extractionPathType === 'fast' 
                        ? 'bg-cyan-950 text-cyan-400 border border-cyan-900'
                        : 'bg-amber-950 text-amber-400 border border-amber-900'
                    }`}>
                      {extractionPathType === 'fast' ? 'Direct VTT Parse (Fast)' : 'WhisperX Sub-word Sync (Auto)'}
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950 p-2.5 rounded border border-slate-800 text-[11px] text-slate-400 italic">
                  "{selectedPhrase.text}"
                </div>

                {/* Slicing Sliders */}
                <div className="space-y-4">
                  {/* Start time slider */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[11px] font-mono">
                      <span className="text-slate-400 font-medium">Sample Boundary Start</span>
                      <span className="text-cyan-400 font-bold">{trimStart.toFixed(2)}s</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-slate-500 font-mono">-{phraseTimelinePoints.start - 1.5}s</span>
                      <input
                        type="range"
                        min={phraseTimelinePoints.start - 2}
                        max={phraseTimelinePoints.end - 0.25}
                        step={0.05}
                        value={trimStart}
                        onChange={(e) => handleStartShift(Number(e.target.value))}
                        className="flex-1 accent-cyan-500 h-1 bg-slate-800 rounded cursor-pointer"
                        id="slider-trim-start"
                      />
                      <span className="text-[10px] text-slate-500 font-mono">+{phraseTimelinePoints.end}s</span>
                    </div>
                  </div>

                  {/* End time slider */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[11px] font-mono">
                      <span className="text-slate-400 font-medium">Sample Boundary End</span>
                      <span className="text-cyan-400 font-bold">{trimEnd.toFixed(2)}s</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-slate-500 font-mono">-{phraseTimelinePoints.start}s</span>
                      <input
                        type="range"
                        min={phraseTimelinePoints.start + 0.25}
                        max={phraseTimelinePoints.end + 2}
                        step={0.05}
                        value={trimEnd}
                        onChange={(e) => handleEndShift(Number(e.target.value))}
                        className="flex-1 accent-cyan-500 h-1 bg-slate-800 rounded cursor-pointer"
                        id="slider-trim-end"
                      />
                      <span className="text-[10px] text-slate-500 font-mono">+{phraseTimelinePoints.end + 1.5}s</span>
                    </div>
                  </div>
                </div>

                {/* Display active duration & energy prediction */}
                <div className="grid grid-cols-2 gap-3 bg-slate-950 p-3 rounded border border-slate-800/80 text-center font-mono text-[11px]">
                  <div>
                    <p className="text-slate-500">SLICED DURATION</p>
                    <p className="text-slate-200 font-bold text-xs mt-0.5 text-cyan-400">{currentDuration} Seconds</p>
                  </div>
                  <div>
                    <p className="text-slate-500">EST. SAMPLE SIZE</p>
                    <p className="text-slate-200 font-bold text-xs mt-0.5">{(currentDuration * 44100 * 2 / 1024).toFixed(0)} KB (WAV)</p>
                  </div>
                </div>

                {/* Plugins processing pipeline */}
                <div className="pt-2">
                  <span className="text-[10px] text-slate-500 font-mono uppercase block mb-2 tracking-wide">ENABLED PROCESSING PLUGINS</span>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="flex items-center gap-2 p-2 bg-slate-900/60 border border-slate-800/80 rounded select-none opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={options.voiceIsolation}
                        disabled
                        className="rounded bg-slate-950 border-slate-800 text-cyan-600 focus:ring-0 focus:ring-offset-0 w-3.5 h-3.5 cursor-not-allowed"
                      />
                      <span className="text-[10.5px] text-slate-400">Demucs Isolation</span>
                      <span className="text-[8px] font-bold text-amber-400 bg-amber-950/50 border border-amber-900 px-1.5 py-0.5 rounded uppercase ml-auto">Coming Soon</span>
                    </label>

                    <label className="flex items-center gap-2 p-2 bg-slate-900/60 border border-slate-800/80 rounded select-none opacity-50 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={options.silenceTrimming}
                        disabled
                        className="rounded bg-slate-950 border-slate-800 text-cyan-600 focus:ring-0 focus:ring-offset-0 w-3.5 h-3.5 cursor-not-allowed"
                      />
                      <span className="text-[10.5px] text-slate-400">Silence Trimming</span>
                      <span className="text-[8px] font-bold text-amber-400 bg-amber-950/50 border border-amber-900 px-1.5 py-0.5 rounded uppercase ml-auto">Coming Soon</span>
                    </label>

                    <label className="flex items-center gap-2 p-2 bg-slate-900/60 border border-slate-800/80 rounded cursor-pointer select-none hover:bg-slate-900 transition-colors">
                      <input
                        type="checkbox"
                        checked={options.normalization}
                        onChange={() => setOptions({ ...options, normalization: !options.normalization })}
                        className="rounded bg-slate-950 border-slate-800 text-cyan-600 focus:ring-0 focus:ring-offset-0 w-3.5 h-3.5 cursor-pointer"
                      />
                      <span className="text-[10.5px] text-slate-400">LUF Normalization</span>
                    </label>

                    <label className="flex items-center gap-2 p-2 bg-slate-900/60 border border-slate-800/80 rounded cursor-pointer select-none hover:bg-slate-900 transition-colors">
                      <input
                        type="checkbox"
                        checked={options.fadeInOut}
                        onChange={() => setOptions({ ...options, fadeInOut: !options.fadeInOut })}
                        className="rounded bg-slate-950 border-slate-800 text-cyan-600 focus:ring-0 focus:ring-offset-0 w-3.5 h-3.5 cursor-pointer"
                      />
                      <span className="text-[10.5px] text-slate-400">Linear Fades (0.05s)</span>
                    </label>
                  </div>
                </div>

                {/* Submission CTA Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 mt-4">
                  <button
                    type="button"
                    onClick={() => onPreviewClip?.(video.id, trimStart, trimEnd, selectedPhrase.text, video.title)}
                    className="sm:col-span-2 bg-slate-900 hover:bg-slate-800 hover:text-cyan-400 text-slate-300 font-mono text-xs py-3 rounded-lg border border-slate-800 flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                    title="Preview the exact audio bounds before exporting"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    PREVIEW CUT
                  </button>

                  <button
                    type="button"
                    onClick={handleHarvest}
                    disabled={isHarvesting}
                    className="sm:col-span-3 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs py-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider shadow-lg shadow-cyan-600/10"
                    id="btn-harvest"
                  >
                    {isHarvesting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        HARVESTING...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        Harvest WAV
                      </>
                    )}
                  </button>
                </div>

              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center text-slate-500 h-full">
                <Sliders className="w-6 h-6 text-slate-700 mb-2" />
                <p className="text-xs font-medium">Select a transcript phrase to fine-tune</p>
                <p className="text-[10px] text-slate-600 max-w-[200px] mt-1">Adjust start/end offsets manually before running the isolation pipelines.</p>
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}