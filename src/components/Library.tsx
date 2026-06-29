import React, { useState, useEffect, useRef } from "react";
import { 
  Music, Search, Filter, Play, Pause, Download, Trash2, Tag, Plus, X, 
  Sparkles, CheckCircle2, ChevronRight, Volume2, Flame, RefreshCcw, Loader2
} from "lucide-react";
import { Sample, Tag as TagType } from "../types";

interface LibraryProps {
  refreshTrigger: number;
  onSelectSampleForTrimming?: (sample: Sample) => void;
  onPreviewClip?: (videoId: string, startTime: number, endTime: number, phraseText: string, sourceTitle: string) => void;
  activePreviewId?: string | null;
}

export default function Library({ 
  refreshTrigger, 
  onSelectSampleForTrimming, 
  onPreviewClip, 
  activePreviewId 
}: LibraryProps) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [tagFacets, setTagFacets] = useState<Record<string, string[]>>({});
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedTagValue, setSelectedTagValue] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);

  // Audio Playback state
  const [playingSampleId, setPlayingSampleId] = useState<string | null>(null);
  const [audioProgress, setAudioProgress] = useState<number>(0); // 0 to 1
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressIntervalRef = useRef<any>(null);
  const speechUtteranceRef = useRef<any>(null);

  // Vocal isolation state
  const [isolatingIds, setIsolatingIds] = useState<Record<string, boolean>>({});
  const [isolationErrors, setIsolationErrors] = useState<Record<string, string>>({});

  // Custom Tag form states
  const [addingTagSampleId, setAddingTagSampleId] = useState<string | null>(null);
  const [newTagCategory, setNewTagCategory] = useState("emotion");
  const [newTagValue, setNewTagValue] = useState("");

  // Polling state
  const [isolationJobs, setIsolationJobs] = useState<Record<string, { jobId: string; status: string; error?: string }>>({});
  const pollingIntervalsRef = useRef<{ [sampleId: string]: NodeJS.Timeout | null }>({});
  const pollingStartTimesRef = useRef<{ [sampleId: string]: number }>({});

  const fetchLibrary = async () => {
    setIsLoading(true);
    try {
      let url = "/api/samples?";
      const params = new URLSearchParams();
      if (searchTerm) params.append("q", searchTerm);
      if (selectedCategory) params.append("category", selectedCategory);
      if (selectedTagValue) params.append("value", selectedTagValue);
      
      const res = await fetch(url + params.toString());
      if (res.ok) {
        const data = await res.json();
        setSamples(data.samples || []);
        setTagFacets(data.tagFacets || {});
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLibrary();
  }, [refreshTrigger, selectedCategory, selectedTagValue]);

  // Handle search with slight debounce/manual trigger to avoid heavy requests
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchLibrary();
  };

  // Playhead progress tracking aligned to the parent's active preview segment
  useEffect(() => {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current);
    }
    setAudioProgress(0);

    if (!activePreviewId) {
      return;
    }

    // Find if the currently previewed item is in our library lists to drive its waveform progress sequence
    const activeSample = samples.find(s => `${s.video_id}-${s.start_time}` === activePreviewId);
    if (!activeSample) return;

    const durationMs = activeSample.duration * 1000;
    const startTimeStamp = Date.now();

    progressIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - startTimeStamp;
      const ratio = Math.min(1.0, elapsed / durationMs);
      setAudioProgress(ratio);

      if (ratio >= 1.0) {
        clearInterval(progressIntervalRef.current);
      }
    }, 50);

    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    };
  }, [activePreviewId, samples]);

  // Command-line play/pause dispatcher mapping onto parents active Acoustic Monitor state
  const handleTogglePlay = (sample: Sample) => {
    const uniqueId = `${sample.video_id}-${sample.start_time}`;
    if (activePreviewId === uniqueId) {
      // Toggle play off by passing empty parameters
      onPreviewClip?.("", 0, 0, "", "");
    } else {
      const endSec = sample.start_time + sample.duration;
      onPreviewClip?.(sample.video_id, sample.start_time, endSec, sample.phrase_text, sample.video_title);
    }
  };

  useEffect(() => {
    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    };
  }, []);

  const handleDeleteSample = async (sampleId: string, videoId: string, startTime: number) => {
    if (!confirm("Are you sure you want to permanently delete this harvested sample?")) {
      return;
    }
    try {
      const res = await fetch(`/api/samples/${sampleId}`, { method: "DELETE" });
      if (res.ok) {
        if (activePreviewId === `${videoId}-${startTime}`) {
          onPreviewClip?.("", 0, 0, "", "");
        }
        fetchLibrary();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddCustomTag = async (sampleId: string) => {
    if (!newTagValue.trim()) return;

    try {
      const res = await fetch(`/api/samples/${sampleId}/tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: newTagCategory, value: newTagValue.trim() })
      });
      if (res.ok) {
        setAddingTagSampleId(null);
        setNewTagValue("");
        fetchLibrary();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteTag = async (sampleId: string, tagId: string) => {
    try {
      const res = await fetch(`/api/samples/${sampleId}/tags/${tagId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        fetchLibrary();
      }
    } catch (e) {
      console.error(e);
    }
  };

  /** Trigger vocal isolation for a sample via POST /api/samples/:id/isolate */
  const handleIsolateVocals = async (sampleId: string) => {
    setIsolatingIds((prev) => ({ ...prev, [sampleId]: true }));
    setIsolationErrors((prev) => {
      const next = { ...prev };
      delete next[sampleId];
      return next;
    });

    try {
      const res = await fetch(`/api/samples/${sampleId}/isolate`, {
        method: "POST",
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const msg = body?.error || `Request failed (${res.status})`;
        setIsolationErrors((prev) => ({ ...prev, [sampleId]: msg }));
        setIsolatingIds((prev) => ({ ...prev, [sampleId]: false }));
        return;
      }

      const data = await res.json();
      if (data.jobId) {
        startPolling(sampleId, data.jobId);
      }
    } catch (e: any) {
      const msg = e?.message || "Network error";
      setIsolationErrors((prev) => ({ ...prev, [sampleId]: msg }));
      setIsolatingIds((prev) => ({ ...prev, [sampleId]: false }));
    }
  };

  /** Start polling GET /api/jobs/:jobId every 3s with a 180s timeout */
  const startPolling = (sampleId: string, jobId: string) => {
    pollingStartTimesRef.current[sampleId] = Date.now();
    setIsolationJobs((prev) => ({ ...prev, [sampleId]: { jobId, status: "pending" } }));

    pollingIntervalsRef.current[sampleId] = setInterval(async () => {
      const elapsed = Date.now() - (pollingStartTimesRef.current[sampleId] || 0);

      // 180s timeout — stop polling and show timeout error
      if (elapsed >= 180000) {
        stopPolling(sampleId);
        setIsolatingIds((prev) => ({ ...prev, [sampleId]: false }));
        setIsolationErrors((prev) => ({ ...prev, [sampleId]: "Operation timed out after 180 seconds" }));
        setIsolationJobs((prev) => {
          const next = { ...prev };
          delete next[sampleId];
          return next;
        });
        return;
      }

      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return; // Transient error — keep polling

        const data = await res.json();
        setIsolationJobs((prev) => ({ ...prev, [sampleId]: { jobId, status: data.status, error: data.error } }));

        if (data.status === "completed") {
          stopPolling(sampleId);
          setIsolatingIds((prev) => ({ ...prev, [sampleId]: false }));
          setIsolationJobs((prev) => {
            const next = { ...prev };
            delete next[sampleId];
            return next;
          });
          fetchLibrary();
        } else if (data.status === "failed") {
          stopPolling(sampleId);
          setIsolatingIds((prev) => ({ ...prev, [sampleId]: false }));
          setIsolationErrors((prev) => ({
            ...prev,
            [sampleId]: data.error || "Isolation failed",
          }));
          setIsolationJobs((prev) => {
            const next = { ...prev };
            delete next[sampleId];
            return next;
          });
        }
      } catch {
        // Network error during poll — continue polling, don't abort
      }
    }, 3000);
  };

  /** Stop polling for a specific sample and clean up refs */
  const stopPolling = (sampleId: string) => {
    if (pollingIntervalsRef.current[sampleId]) {
      clearInterval(pollingIntervalsRef.current[sampleId]!);
      delete pollingIntervalsRef.current[sampleId];
    }
    delete pollingStartTimesRef.current[sampleId];
  };

  // Clean up all polling intervals on unmount
  useEffect(() => {
    return () => {
      Object.keys(pollingIntervalsRef.current).forEach((id) => {
        if (pollingIntervalsRef.current[id]) {
          clearInterval(pollingIntervalsRef.current[id]!);
        }
      });
      pollingIntervalsRef.current = {};
      pollingStartTimesRef.current = {};
    };
  }, []);

  const clearFacets = () => {
    setSelectedCategory("");
    setSelectedTagValue("");
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl" id="vocal-harvester-library">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Music className="w-5 h-5 text-cyan-400" />
          <div>
            <h2 className="text-lg font-medium text-slate-100 tracking-tight">3. Harvested Vocal Library</h2>
            <p className="text-[10px] text-slate-400 mt-0.5">High Fidelity 24-bit PCM samples mapped onto immediate trigger paths</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => fetchLibrary()}
            className="p-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition-colors"
            title="Refresh database state"
          >
            <RefreshCcw className="w-4 h-4" />
          </button>
          <span className="text-[10px] font-mono bg-slate-950 text-slate-400 px-2.5 py-1 rounded border border-slate-800">
            TOTAL HARVESTED: {samples.length} SAMPLES
          </span>
        </div>
      </div>

      {/* Local Searching & SQLite FTS matching filters */}
      <div className="space-y-4 mb-6">
        <form onSubmit={handleSearchSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Full-test matching (FTS5) for specific transcript phrases or video titles..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 rounded-lg pl-9 pr-4 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-all font-mono"
              id="library-search-input"
            />
            <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-500" />
          </div>
          <button
            type="submit"
            className="bg-slate-950 hover:bg-slate-800 text-slate-300 font-mono text-xs px-4 py-2 rounded-lg border border-slate-800 transition cursor-pointer"
          >
            SEARCH
          </button>
        </form>

        {/* Tag Filters (Facets) */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-semibold font-mono text-slate-500 flex items-center gap-1">
            <Filter className="w-3 h-3" /> CATEGORIES:
          </span>

          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Quick selections for categories in the database */}
            {Object.keys(tagFacets).map((category) => {
              const values = tagFacets[category];
              return (
                <div key={category} className="inline-flex items-center rounded-md bg-slate-950 border border-slate-800 overflow-hidden text-[10.5px]">
                  <span className="text-slate-500 px-2 py-0.5 border-r border-slate-800 lowercase font-mono">
                    {category}
                  </span>
                  <select
                    value={selectedCategory === category ? selectedTagValue : ""}
                    onChange={(e) => {
                      if (e.target.value) {
                        setSelectedCategory(category);
                        setSelectedTagValue(e.target.value);
                      } else {
                        clearFacets();
                      }
                    }}
                    className="bg-slate-950 text-slate-300 px-2 py-0.5 focus:outline-none font-mono cursor-pointer outline-none border-none text-[10px]"
                  >
                    <option value="">Any</option>
                    {values.map(val => (
                      <option key={val} value={val}>{val}</option>
                    ))}
                  </select>
                </div>
              );
            })}

            {(selectedCategory || searchTerm) && (
              <button
                onClick={() => {
                  clearFacets();
                  setSearchTerm("");
                  setTimeout(() => fetchLibrary(), 50);
                }}
                className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 pl-2 cursor-pointer flex items-center gap-1"
              >
                Clear Filters <X className="w-2.5 h-2.5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Loader2 className="w-7 h-7 text-cyan-500 animate-spin mb-2" />
          <span className="text-[11px] font-mono text-slate-400">LOADING HARVESTED DATABASE CHUNKS...</span>
        </div>
      ) : samples.length === 0 ? (
        <div className="text-center py-12 bg-slate-950/20 border border-dashed border-slate-800 rounded-lg">
          <Music className="w-8 h-8 text-slate-700 mx-auto mb-2.5 animate-pulse" />
          <p className="text-xs text-slate-400">Your Vocal Harvester library is currently empty.</p>
          <p className="text-[10px] text-slate-500 max-w-xs mx-auto mt-1">Search YouTube sources in Section 1 and submit active alignment clipping tasks to build your audio sample library.</p>
        </div>
      ) : (
        <div className="space-y-4" id="samples-masonry-list">
          {samples.map((sample) => {
            const isPlaying = activePreviewId === `${sample.video_id}-${sample.start_time}`;
            const isAddingTag = addingTagSampleId === sample.id;
            const isIsolatingSample = isolatingIds[sample.id];
            const isolationError = isolationErrors[sample.id];
            const jobInfo = isolationJobs[sample.id];

            return (
              <div 
                key={sample.id} 
                className={`bg-slate-950 border rounded-lg p-4 transition-all ${
                  isPlaying 
                    ? "border-cyan-500/90 shadow-md shadow-cyan-500/5 bg-slate-950" 
                    : "border-slate-800 hover:border-slate-700/80"
                }`}
                id={`sample-card-${sample.id}`}
              >
                
                {/* Header Information */}
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-3 mb-3 pb-2 border-b border-slate-900">
                  <div className="min-w-0 flex-1">
                    <span className="text-[8.5px] font-semibold font-mono bg-slate-900 border border-slate-800 text-slate-400 px-1.5 py-0.5 rounded uppercase">
                      {sample.id}
                    </span>
                    <h3 className="text-xs font-semibold text-slate-100 mt-1 mr-2 leading-relaxed">
                      "{sample.phrase_text}"
                    </h3>
                    <p className="text-[9.5px] font-mono text-slate-500 mt-1 truncate">
                      Source video: <span className="text-slate-400 font-medium">{sample.video_title}</span> ({sample.video_id})
                    </p>
                  </div>

                  <div className="flex items-center gap-1.5 flex-shrink-0 self-end md:self-start">
                    {/* Energy score indicator */}
                    <div className="flex items-center gap-1 bg-slate-900/60 border border-slate-800 px-2 py-0.5 rounded font-mono text-[9px] text-amber-500">
                      <Flame className="w-3 h-3" />
                      <span>{sample.energy_score || '0.50'} EQ</span>
                    </div>

                    <span className="text-[10px] font-mono text-slate-500 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">
                      {sample.duration}s
                    </span>

                    <a 
                      href={`/api/samples/audio/${sample.id}`}
                      download={`${sample.id}.wav`}
                      className="p-1 px-1.5 text-xs text-slate-400 hover:text-slate-100 bg-slate-900 border border-slate-800 hover:border-slate-700 rounded transition"
                      title="Download clean WAV sample"
                    >
                      <Download className="w-3.5 h-3.5 inline mr-1" />
                      <span className="text-[9px] font-mono">WAV</span>
                    </a>

                    {/* Isolate Vocals Button */}
                    {!sample.isolated_path && (
                      <button
                        onClick={() => handleIsolateVocals(sample.id)}
                        disabled={isIsolatingSample}
                        className={`p-1 px-1.5 text-xs text-slate-400 hover:text-slate-100 bg-slate-900 border border-slate-800 hover:border-slate-700 rounded transition flex items-center gap-1 ${
                          isIsolatingSample ? 'opacity-50 cursor-not-allowed' : ''
                        }`}
                        title="Isolate vocals using AI"
                      >
                        {isIsolatingSample ? (
                          <>
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            <span className="text-[9px] font-mono">Isolating...</span>
                          </>
                        ) : (
                          <>
                            <Sparkles className="w-3.5 h-3.5" />
                            <span className="text-[9px] font-mono">Isolate</span>
                          </>
                        )}
                      </button>
                    )}

                    <button 
                      onClick={() => handleDeleteSample(sample.id, sample.video_id, sample.start_time)}
                      className="p-1 text-slate-500 hover:text-red-400 hover:bg-red-950/20 rounded transition"
                      title="Delete sample"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Waveform peak viewer */}
                <div 
                  className="bg-slate-950/40 relative h-12 rounded border border-slate-900/80 mb-3 flex items-center justify-around px-2 overflow-hidden group cursor-pointer"
                  onClick={() => handleTogglePlay(sample)}
                >
                  {/* Procedural peaks */}
                  <div className="absolute inset-0 flex items-center justify-around px-4 pointer-events-none opacity-80">
                    {Array.from({ length: 65 }).map((_, peakIdx) => {
                      // Generate reproducible shape based on sample phrase text
                      const charCode = sample.phrase_text.charCodeAt(peakIdx % sample.phrase_text.length) || 45;
                      const factor = Math.abs(Math.sin(peakIdx * 0.12) * Math.cos(peakIdx * 0.08));
                      let amplitude = (charCode % 10 + 1) * 0.1 * factor * 0.95;
                      
                      // Shape taper at start/end
                      if (peakIdx < 5) amplitude *= (peakIdx / 5);
                      if (peakIdx > 60) amplitude *= ((65 - peakIdx) / 5);
                      
                      const heightPercent = Math.max(8, Math.floor(amplitude * 100));
                      const isPlayedPast = isPlaying && (peakIdx / 65) < audioProgress;

                      return (
                        <div 
                          key={peakIdx} 
                          className={`w-1 rounded-sm transition-all duration-150 ${
                            isPlayedPast 
                              ? "bg-cyan-400" 
                              : isPlaying 
                                ? "bg-slate-700" 
                                : "bg-slate-800 group-hover:bg-slate-700"
                          }`}
                          style={{ height: `${heightPercent}%` }}
                        ></div>
                      );
                    })}
                  </div>

                  {/* Playhead slider marker */}
                  {isPlaying && (
                    <div 
                      className="absolute top-0 bottom-0 w-0.5 bg-cyan-400/90 z-10 pointer-events-none"
                      style={{ left: `${audioProgress * 100}%` }}
                    ></div>
                  )}

                  {/* Quick Play overlay icon trigger */}
                  <div className="absolute left-3 top-2 bg-slate-950/80 hover:bg-slate-950 text-slate-100 p-1.5 rounded-full border border-slate-800 transition flex items-center gap-1.5 z-20">
                    {isPlaying ? (
                      <Pause className="w-3 h-3 text-cyan-400 fill-cyan-400" />
                    ) : (
                      <Play className="w-3 h-3 text-slate-200 fill-slate-200" />
                    )}
                    <span className="text-[9px] font-mono pr-1 text-slate-300">
                      {isPlaying ? `${Math.floor(audioProgress * 100)}%` : "PREVIEW AUDIO"}
                    </span>
                  </div>

                  <span className="absolute right-3.5 bottom-1.5 text-[8.5px] font-mono text-slate-500 select-none">
                    44.1kHz • Mono PCM
                  </span>
                </div>

                {/* Metadata Tags lists */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                  
                  {/* Assigned Tags pills */}
                  <div className="flex flex-wrap gap-1.5 items-center">
                    <span className="text-[9px] text-slate-500 font-mono flex items-center gap-1">
                      <Tag className="w-2.5 h-2.5" /> TAGS:
                    </span>

                    {sample.tags?.map((t: TagType) => (
                      <span 
                        key={t.id} 
                        className="text-[9.5px] font-mono bg-slate-900 border border-slate-800/80 text-cyan-400 px-2 py-0.5 rounded flex items-center gap-1 group/pill hover:border-red-500/40 transition-colors"
                      >
                        <span className="text-slate-500 lowercase">{t.category}:</span>{t.value}
                        <button
                          onClick={() => handleDeleteTag(sample.id, t.id)}
                          className="text-slate-500 hover:text-red-400 focus:outline-none transition opacity-60 group-hover/pill:opacity-100 font-bold"
                          title="Remove metadata tag"
                        >
                          <X className="w-2 h-2" />
                        </button>
                      </span>
                    ))}

                    {!isAddingTag && (
                      <button
                        onClick={() => setAddingTagSampleId(sample.id)}
                        className="text-[9px] font-mono text-slate-500 hover:text-slate-300 bg-slate-900 hover:bg-slate-900/80 px-2 py-0.5 rounded border border-slate-800/80 transition-colors flex items-center gap-0.5 cursor-pointer"
                      >
                        <Plus className="w-2.5 h-2.5" /> add tag
                      </button>
                    )}
                  </div>

                  {/* DAW Mapping configuration helpful note tags */}
                  <div className="text-[9.2px] font-mono text-slate-500">
                    {sample.is_processed ? (
                      <span className="text-emerald-500 flex items-center gap-1 font-semibold">
                        <CheckCircle2 className="w-3 h-3 text-emerald-500" /> DAWS BOUND
                      </span>
                    ) : (
                      <span>RAW EXTRACTION</span>
                    )}
                  </div>
                </div>

                {/* Isolation Error Message */}
                {isolationError && (
                  <div className="mt-2 text-[10px] text-red-400 bg-red-950/20 border border-red-900/30 rounded px-2 py-1">
                    {isolationError}
                  </div>
                )}

                {/* Isolation Job Status */}
                {jobInfo && (
                  <div className="mt-2 text-[10px] font-mono text-slate-300 bg-slate-900/40 border border-slate-800/50 rounded px-2 py-1 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />
                    <span className="text-slate-400">Status:</span>
                    <span className="text-cyan-300">{jobInfo.status}</span>
                  </div>
                )}

                {/* Embedded dynamic custom tag builder inline */}
                {isAddingTag && (
                  <div className="mt-3 p-3 bg-slate-900/60 rounded border border-slate-800/80 flex items-center gap-2.5 flex-wrap">
                    <span className="text-[10px] font-mono text-slate-400">Add metadata category:</span>
                    
                    <select
                      value={newTagCategory}
                      onChange={(e) => setNewTagCategory(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-slate-300 px-2 py-1 rounded text-xs focus:outline-none font-mono"
                    >
                      <option value="emotion">emotion</option>
                      <option value="gender">gender</option>
                      <option value="role">role (speaker role)</option>
                      <option value="note">musical note</option>
                      <option value="genre">genre styling</option>
                    </select>

                    <input
                      type="text"
                      placeholder="e.g. ecstatic, low-mid pitch, robot..."
                      value={newTagValue}
                      onChange={(e) => setNewTagValue(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 px-2 py-1 rounded text-xs focus:outline-none flex-1 min-w-[120px] font-mono"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleAddCustomTag(sample.id);
                      }}
                    />

                    <div className="flex gap-1">
                      <button
                        onClick={() => handleAddCustomTag(sample.id)}
                        className="bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-[10px] py-1 px-3 rounded tracking-wider transition uppercase"
                      >
                        Apply
                      </button>
                      <button
                        onClick={() => {
                          setAddingTagSampleId(null);
                          setNewTagValue("");
                        }}
                        className="bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 px-2.5 py-1 rounded text-[10px] transition"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}