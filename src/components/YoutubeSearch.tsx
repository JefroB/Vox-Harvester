import React, { useState } from "react";
import { Search, Youtube, Check, Loader2 } from "lucide-react";
import { VideoMeta } from "../types";

interface YoutubeSearchProps {
  onSelectVideo: (video: VideoMeta) => void;
  selectedVideoId: string | null;
}

export default function YoutubeSearch({ onSelectVideo, selectedVideoId }: YoutubeSearchProps) {
  const [query, setQuery] = useState("");
  const [enforceClosedCaptions, setEnforceClosedCaptions] = useState(true);
  const [videos, setVideos] = useState<VideoMeta[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    try {
      // Direct YouTube URL parsing regex
      const ytRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/i;
      const urlMatch = query.match(ytRegex);

      if (urlMatch && urlMatch[1]) {
        const extractedId = urlMatch[1];
        // Query the search endpoint to fetch grounded metadata for this specific ID
        const response = await fetch("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: `Video ID ${extractedId}` }),
        });
        const data = await response.json();
        
        // Find if returned results match or construct high-quality direct metadata
        const matchedVideo = data.results?.find((v: any) => v.id === extractedId) || {
          id: extractedId,
          title: "Imported Spoken Segment",
          channelName: "YouTube Archive",
          duration: "10:00",
          description: "Manually loaded direct URL video resource.",
          thumbnailUrl: `https://img.youtube.com/vi/${extractedId}/mqdefault.jpg`
        };

        setVideos([matchedVideo]);
        setHasSearched(true);
        onSelectVideo(matchedVideo);
      } else {
        // Standard textual keyword search priority
        const searchQuery = enforceClosedCaptions 
          ? `${query} "closed captions"` 
          : query;

        const response = await fetch("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: searchQuery }),
        });
        const data = await response.json();
        setVideos(data.results || []);
        setHasSearched(true);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl" id="yt-search-container">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Youtube className="w-5 h-5 text-red-500" />
          <h2 className="text-lg font-medium text-slate-100 tracking-tight font-sans">1. Source Aquisition</h2>
        </div>
        <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
          Cobalt Engine Active
        </span>
      </div>

      <form onSubmit={handleSearch} className="space-y-4">
        <div className="relative">
          <input
            type="text"
            className="w-full bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 rounded-lg pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500 focus:border-cyan-500 transition-all font-sans"
            placeholder="Search keywords OR paste direct YouTube URL link..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            id="yt-search-input"
          />
          <Search className="absolute left-3.5 top-3.5 w-4 h-4 text-slate-500" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <label className="flex items-center gap-2.5 cursor-pointer text-xs text-slate-400 hover:text-slate-200 select-none font-sans">
            <input
              type="checkbox"
              className="rounded bg-slate-950 border-slate-800 text-cyan-600 focus:ring-cyan-500 focus:ring-offset-slate-900 focus:ring-0 w-4 h-4 cursor-pointer"
              checked={enforceClosedCaptions}
              onChange={() => setEnforceClosedCaptions(!enforceClosedCaptions)}
            />
            <span className="flex items-center gap-1.5 matches-label">
              <span>Filter Spoken Lectures &amp; Keynotes Priority</span>
              <code className="text-[10px] bg-slate-950 text-cyan-500 px-1 py-0.2 rounded font-mono border border-slate-800">
                &amp;sp=EgQQASgB
              </code>
            </span>
          </label>

          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold font-mono text-[11px] px-5 py-2 rounded-lg flex items-center gap-2 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Search className="w-3.5 h-3.5" />
                Find / Load URL
              </>
            )}
          </button>
        </div>
      </form>

      {/* Video Results List */}
      {hasSearched && (
        <div className="mt-5 pt-5 border-t border-slate-800 space-y-3 font-sans" id="yt-search-results">
          <div className="flex items-center justify-between text-xs text-slate-500 font-mono mb-2">
            <span>RESULTS FOUND: {videos.length}</span>
            <span>CLICK TO SEED CAPTION RETRIEVAL</span>
          </div>

          {videos.length === 0 ? (
            <div className="text-center py-6 text-sm text-slate-500">
              No matching YouTube sources found. Try expanding your search queries.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {videos.map((vid) => {
                const isSelected = selectedVideoId === vid.id;
                return (
                  <div
                    key={vid.id}
                    onClick={() => onSelectVideo(vid)}
                    className={`group cursor-pointer rounded-lg overflow-hidden border p-3 flex gap-3 transition-all ${
                      isSelected
                        ? "bg-slate-950 border-cyan-500/80 shadow-md shadow-cyan-500/5"
                        : "bg-slate-950/50 border-slate-800 hover:border-slate-700 hover:bg-slate-950"
                    }`}
                  >
                    {/* Thumbnail representation */}
                    <div className="relative w-20 h-14 flex-shrink-0 bg-slate-900 rounded overflow-hidden border border-slate-800 flex items-center justify-center">
                      {vid.thumbnailUrl && vid.thumbnailUrl.startsWith("http") ? (
                        <img
                          src={vid.thumbnailUrl}
                          alt={vid.title}
                          referrerPolicy="no-referrer"
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                        />
                      ) : (
                        <Youtube className="w-5 h-5 text-slate-700" />
                      )}
                      <span className="absolute bottom-0.5 right-0.5 text-[8.5px] font-mono bg-slate-950/90 text-slate-300 px-1 py-0.2 rounded-sm border border-slate-800">
                        {vid.duration}
                      </span>
                    </div>

                    <div className="min-w-0 flex-1 flex flex-col justify-between">
                      <div>
                        <h4 className="text-xs font-semibold text-slate-200 truncate group-hover:text-cyan-400 transition-colors leading-snug">
                          {vid.title}
                        </h4>
                        <p className="text-[10px] text-slate-400 mt-0.5 tracking-tight font-medium">
                          {vid.channelName}
                        </p>
                      </div>
                      <div className="flex items-center justify-between mt-1 text-[9px] font-mono">
                        <span className="text-slate-500">{vid.id}</span>
                        {isSelected ? (
                          <span className="text-cyan-500 flex items-center gap-0.5 font-bold uppercase text-[8px] tracking-widest">
                            <Check className="w-2.5 h-2.5" /> Selected
                          </span>
                        ) : (
                          <span className="text-slate-600 group-hover:text-slate-400 uppercase tracking-widest text-[8px]">
                            Load phrases
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
