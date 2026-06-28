import React, { useEffect, useState } from "react";
import { Loader2, Activity, CheckCircle, XCircle, Clock } from "lucide-react";
import { JobStatus } from "../types";

interface ActiveJobsProps {
  jobIds: string[];
  onJobCompleted: (sampleId: string) => void;
  onJobRemoved: (jobId: string) => void;
}

export default function ActiveJobs({ jobIds, onJobCompleted, onJobRemoved }: ActiveJobsProps) {
  const [jobStatuses, setJobStatuses] = useState<Record<string, JobStatus>>({});

  useEffect(() => {
    if (jobIds.length === 0) return;

    const activeIds = jobIds.filter(id => {
      const job = jobStatuses[id];
      return !job || (job.status !== "completed" && job.status !== "failed");
    });

    if (activeIds.length === 0) return;

    // Poll status of all non-completed/failed jobs
    const interval = setInterval(async () => {
      for (const id of activeIds) {
        try {
          const res = await fetch(`/api/jobs/${id}`);
          if (res.ok) {
            const data: JobStatus = await res.json();
            setJobStatuses(prev => {
              const isNewCompletion = data.status === "completed" && data.resultSampleId && (!prev[id] || prev[id].status !== "completed");
              if (isNewCompletion) {
                // Defer side effect execution safely outside the React synchronization update cycle
                setTimeout(() => {
                  onJobCompleted(data.resultSampleId!);
                }, 0);
              }
              return { ...prev, [id]: data };
            });
          }
        } catch (e) {
          console.error(`Error polling job ${id}:`, e);
        }
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [jobIds, jobStatuses, onJobCompleted]);

  // Initial fetch for newly added jobs
  useEffect(() => {
    const missingIds = jobIds.filter(id => !jobStatuses[id]);
    missingIds.forEach(async (id) => {
      try {
        const res = await fetch(`/api/jobs/${id}`);
        if (res.ok) {
          const data: JobStatus = await res.json();
          setJobStatuses(prev => ({ ...prev, [id]: data }));
        }
      } catch (e) {
        console.error(e);
      }
    });
  }, [jobIds, jobStatuses]);

  if (jobIds.length === 0) return null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl" id="active-jobs-panel">
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-amber-500 animate-pulse" />
          <h2 className="text-lg font-medium text-slate-100 tracking-tight">Active Background Processing Queue</h2>
        </div>
        <span className="text-[10px] font-mono bg-amber-950/30 text-amber-400 px-2.5 py-0.5 rounded border border-amber-900">
          Async Queue Worker
        </span>
      </div>

      <div className="space-y-3">
        {jobIds.map(id => {
          const job = jobStatuses[id];
          if (!job) return null;

          const isPending = job.status === "pending";
          const isProcessing = job.status === "processing";
          const isCompleted = job.status === "completed";
          const isFailed = job.status === "failed";

          return (
            <div 
              key={id} 
              className="bg-slate-950 border border-slate-800/80 rounded-lg p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 transition-colors"
              id={`job-row-${id}`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className={`text-[9px] font-bold px-1.5 py-0.2 rounded font-mono uppercase ${
                    isCompleted ? "bg-emerald-950/50 text-emerald-400 border border-emerald-900" :
                    isFailed ? "bg-red-950/50 text-red-400 border border-red-900" :
                    "bg-amber-950/50 text-amber-400 border border-amber-900"
                  }`}>
                    {job.status}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">ID: {job.id}</span>
                  <span className="text-slate-400 text-xs font-semibold truncate max-w-[250px]">"{job.phrase_text}"</span>
                </div>
                
                <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                  <span className="text-slate-300 font-medium">Source:</span> 
                  <span className="truncate">{job.video_title}</span>
                </p>

                {/* Progress message bar */}
                <p className="text-[11px] text-slate-500 mt-1.5 font-mono italic">
                  {job.message}
                </p>

                {/* Progress bar visual */}
                {!isCompleted && !isFailed && (
                  <div className="w-full bg-slate-900 rounded-full h-1 mt-2 overflow-hidden border border-slate-800/50">
                    <div 
                      className="bg-cyan-500 h-full transition-all duration-500 rounded-full" 
                      style={{ width: `${job.progress}%` }}
                    ></div>
                  </div>
                )}
              </div>

              {/* Status Interaction Controls */}
              <div className="flex items-center gap-3 justify-end flex-shrink-0">
                <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400">
                  {isPending && <Clock className="w-3.5 h-3.5 text-slate-500" />}
                  {isProcessing && <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin" />}
                  {isCompleted && <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />}
                  {isFailed && <XCircle className="w-3.5 h-3.5 text-red-500" />}
                  <span>{job.progress}%</span>
                </div>

                <button
                  onClick={() => onJobRemoved(id)}
                  disabled={!isCompleted && !isFailed}
                  className="text-[10px] font-mono text-slate-500 hover:text-slate-300 px-2 py-1 rounded bg-slate-900 border border-slate-800 hover:border-slate-700 transition"
                >
                  Dismiss
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
