import React, { useEffect, useState, useRef } from "react";
import { 
  X, Play, Pause, RotateCcw, Monitor, Sparkles 
} from "lucide-react";

interface AcousticMonitorProps {
  videoId: string;
  startTime: number;
  endTime: number;
  phraseText: string;
  sourceTitle: string;
  onClose: () => void;
}

export default function AcousticMonitor({
  videoId,
  startTime,
  endTime,
  phraseText,
  sourceTitle,
  onClose
}: AcousticMonitorProps) {
  const [useDirectYouTube, setUseDirectYouTube] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const durationSec = Math.max(0.5, endTime - startTime);
  const streamUrl = `/api/audio-stream?videoId=${videoId}&start=${startTime}&end=${endTime}`;

  // Reset state on content change
  useEffect(() => {
    setIsPlaying(false);
    setCurrentTime(0);
    if (useDirectYouTube) {
      setIsLoading(false);
    } else {
      setIsLoading(true);
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.load();
        audioRef.current.play().catch((err) => {
          console.warn("Autoplay block or audio streaming error: ", err);
        });
      }
    }
  }, [useDirectYouTube, videoId, startTime, endTime, streamUrl]);

  // Handle client-side interval-based timeline animation in Direct YouTube mode
  useEffect(() => {
    if (!useDirectYouTube) return;

    let timer: NodeJS.Timeout;
    if (isPlaying) {
      timer = setInterval(() => {
        setCurrentTime((prev) => {
          if (prev >= durationSec) {
            setIsPlaying(false);
            return 0;
          }
          return prev + 0.1;
        });
      }, 100);
    }
    return () => clearInterval(timer);
  }, [isPlaying, useDirectYouTube, durationSec]);

  const handleReplay = () => {
    if (useDirectYouTube) {
      setIsPlaying(false);
      setCurrentTime(0);
      setTimeout(() => {
        setIsPlaying(true);
      }, 50);
    } else {
      if (audioRef.current) {
        audioRef.current.currentTime = 0;
        audioRef.current.play().catch(err => console.error(err));
      }
    }
  };

  const handleTogglePlay = () => {
    if (useDirectYouTube) {
      if (isPlaying) {
        setIsPlaying(false);
      } else {
        if (currentTime >= durationSec) {
          setCurrentTime(0);
        }
        setIsPlaying(true);
      }
    } else {
      if (audioRef.current) {
        if (isPlaying) {
          audioRef.current.pause();
        } else {
          audioRef.current.play().catch(err => console.error(err));
        }
      }
    }
  };

  // Convert start/end to display timestamps (e.g., 01:24.50)
  const formatTime = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 100);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`;
  };

  return (
    <div 
      className="fixed bottom-6 right-6 w-80 bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-2xl shadow-cyan-500/15 z-50 transition-all duration-300 animate-in slide-in-from-bottom-5"
      id="acoustic-monitor-widget"
    >
      {/* Widget Header */}
      <div className="flex items-center justify-between gap-3 mb-2.5 pb-2 border-b border-b-slate-800/80">
        <div className="flex items-center gap-2">
          <div className="relative">
            <span className="absolute -top-1 -right-1 flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isPlaying ? "bg-cyan-400" : "bg-slate-500"}`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${isPlaying ? "bg-cyan-500" : "bg-slate-500"}`}></span>
            </span>
            <Monitor className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h4 className="text-[10px] font-bold font-mono text-slate-200 tracking-wider uppercase">Studio Acoustic Monitor</h4>
            <p className="text-[9px] text-slate-500 font-mono truncate max-w-[180px]">{sourceTitle}</p>
          </div>
        </div>

        <button 
          onClick={onClose} 
          className="p-1 rounded bg-transparent border-0 hover:bg-slate-800 text-slate-500 hover:text-slate-200 transition cursor-pointer"
          title="Close Monitor"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* High-Fidelity Audio Mode Selector Toggle */}
      <div className="flex items-center justify-between bg-slate-950 p-1 rounded-lg border border-slate-800/80 gap-1 mb-3">
        <button
          onClick={() => setUseDirectYouTube(true)}
          className={`flex-1 py-1 text-[8.5px] font-mono font-bold rounded transition cursor-pointer text-center select-none ${
            useDirectYouTube 
              ? "bg-cyan-500 text-slate-950" 
              : "bg-transparent text-slate-400 hover:text-slate-200"
          }`}
          title="Play raw high-fidelity audio directly from YouTube in your browser (guaranteed unblocked)"
        >
          DIRECT YT STREAM
        </button>
        <button
          onClick={() => setUseDirectYouTube(false)}
          className={`flex-1 py-1 text-[8.5px] font-mono font-bold rounded transition cursor-pointer text-center select-none ${
            !useDirectYouTube 
              ? "bg-cyan-500 text-slate-950" 
              : "bg-transparent text-slate-400 hover:text-slate-200"
          }`}
          title="Play voice-isolated, normalized WAV stream downloaded by local server"
        >
          ISOLATED SERVER WAV
        </button>
      </div>

      {/* Hidden Unblocked Direct YouTube player IFrame */}
      {useDirectYouTube && isPlaying && (
        <iframe
          src={`https://www.youtube.com/embed/${videoId}?start=${Math.floor(startTime)}&end=${Math.ceil(endTime)}&autoplay=1&mute=0&controls=0&modestbranding=1&rel=0`}
          allow="autoplay"
          className="w-1 h-1 absolute -top-[9999px] -left-[9999px] pointer-events-none opacity-0 invisible"
        />
      )}

      {/* High-Fidelity Audio Scope / Tape Deck Representational Interface */}
      <div className="relative aspect-video w-full bg-slate-950 rounded-lg overflow-hidden border border-slate-950 shadow-inner flex flex-col items-center justify-center p-3">
        {!useDirectYouTube && (
          <audio
            ref={audioRef}
            src={streamUrl}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => setIsPlaying(false)}
            onTimeUpdate={() => {
              if (audioRef.current) {
                setCurrentTime(audioRef.current.currentTime);
              }
            }}
            onCanPlay={() => setIsLoading(false)}
            autoPlay
          />
        )}

        {isLoading ? (
          <div className="flex flex-col items-center justify-center text-center gap-2.5">
            <div className="relative flex items-center justify-center">
              <div className="w-9 h-9 border-2 border-cyan-500/10 border-t-cyan-500 rounded-full animate-spin"></div>
              <Sparkles className="w-4 h-4 text-cyan-400 absolute animate-pulse" />
            </div>
            <div className="space-y-0.5">
              <span className="text-[10px] uppercase font-mono text-cyan-400 tracking-wider font-bold animate-pulse">STREAMING REAL AUDIO...</span>
              <p className="text-[8.5px] text-slate-500 font-mono leading-tight">Slicing high-fidelity vocal track from YouTube.</p>
            </div>
          </div>
        ) : (
          <div className="w-full h-full flex flex-col justify-between relative">
            {/* Vintage Tape Reels simulation */}
            <div className="flex-1 flex items-center justify-center gap-10 py-1 select-none">
              <div 
                className="w-14 h-14 rounded-full border-4 border-slate-800 bg-slate-950 flex items-center justify-center shadow-lg shadow-black/80 ring-1 ring-cyan-500/10 relative"
                style={{
                  transform: `rotate(${currentTime * 120}deg)`,
                  transition: isPlaying ? "none" : "transform 0.4s ease"
                }}
              >
                {/* Visual Reel Spikes */}
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-0"></div>
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-45"></div>
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-90"></div>
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-135"></div>
                <div className="w-5 h-5 rounded-full bg-slate-900 border border-slate-800 z-10 flex items-center justify-center">
                  <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full"></div>
                </div>
              </div>

              <div 
                className="w-14 h-14 rounded-full border-4 border-slate-800 bg-slate-950 flex items-center justify-center shadow-lg shadow-black/80 ring-1 ring-cyan-500/10 relative"
                style={{
                  transform: `rotate(${currentTime * 120}deg)`,
                  transition: isPlaying ? "none" : "transform 0.4s ease"
                }}
              >
                {/* Visual Reel Spikes */}
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-0"></div>
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-45"></div>
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-90"></div>
                <div className="w-full h-0.5 bg-slate-800 absolute rotate-135"></div>
                <div className="w-5 h-5 rounded-full bg-slate-900 border border-slate-800 z-10 flex items-center justify-center">
                  <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full"></div>
                </div>
              </div>
            </div>

            {/* Playback Timing HUD overlay */}
            <div className="flex items-center justify-between text-[9px] font-mono text-slate-500 px-1 mt-1">
              <span className="text-cyan-500 font-bold tracking-widest uppercase flex items-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full ${isPlaying ? "bg-cyan-400 animate-pulse" : "bg-slate-600"}`}></span>
                {isPlaying ? "PLAYING" : "READY"}
              </span>
              <span>{currentTime.toFixed(2)}s / {durationSec.toFixed(2)}s</span>
            </div>
          </div>
        )}
      </div>

      {/* Subtitles / Speech Text Box */}
      <div className="mt-3 bg-slate-950/90 border border-slate-800/60 rounded px-2.5 py-2 font-medium text-[11px] text-slate-200 leading-relaxed text-center italic min-h-[44px] flex items-center justify-center select-none">
        "{phraseText}"
      </div>

      {/* Audio Waveform/Analyser visualization feedback */}
      <div className="mt-2.5 h-6 bg-slate-950/60 rounded border border-slate-800/40 flex items-center justify-around px-2 overflow-hidden select-none">
        {Array.from({ length: 24 }).map((_, idx) => {
          const delay = `${(idx % 4) * 0.15}s`;
          const duration = `${0.35 + (idx % 3) * 0.12}s`;
          return (
            <div
              key={idx}
              className="w-1 rounded-full bg-cyan-500/80"
              style={{
                height: isPlaying ? "85%" : "15%",
                opacity: isPlaying ? 0.9 : 0.25,
                animation: isPlaying ? `bounce ${duration} ease-in-out infinite alternate` : "none",
                animationDelay: isPlaying ? delay : "0s"
              }}
            ></div>
          );
        })}
      </div>

      {/* Control Actions & Timing HUD */}
      <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono select-none">
        <div className="flex flex-col">
          <span className="text-[8px] text-slate-500 lowercase">alignment range</span>
          <span className="text-[10px] text-cyan-400 font-bold">{formatTime(startTime)} - {formatTime(endTime)}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={handleTogglePlay}
            disabled={isLoading}
            className="p-1 px-2 rounded bg-slate-800 hover:bg-slate-700 hover:text-white text-slate-200 border border-slate-700 transition flex items-center gap-1 text-[9.5px] uppercase font-bold cursor-pointer disabled:opacity-40"
            title={isPlaying ? "Pause playback" : "Play vocal segment"}
          >
            {isPlaying ? (
              <>
                <Pause className="w-2.5 h-2.5 fill-current" />
                PAUSE
              </>
            ) : (
              <>
                <Play className="w-2.5 h-2.5 fill-current" />
                PLAY
              </>
            )}
          </button>

          <button
            onClick={handleReplay}
            disabled={isLoading}
            className="p-1 px-2 rounded bg-slate-800 hover:bg-slate-700 hover:text-white text-slate-200 border border-slate-700 transition flex items-center gap-1 text-[9.5px] uppercase font-bold cursor-pointer disabled:opacity-40"
            title="Replay from starting cue point"
          >
            <RotateCcw className="w-2.5 h-2.5" />
            REPLAY
          </button>
        </div>
      </div>

      {/* CSS Bounce Animation for analysis feedback */}
      <style>{`
        @keyframes bounce {
          0% { height: 15%; }
          100% { height: 95%; }
        }
      `}</style>
    </div>
  );
}
