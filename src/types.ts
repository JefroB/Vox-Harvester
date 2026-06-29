/**
 * YouTube Vocal Harvester
 * Shared Types Definition
 */

export interface VideoMeta {
  id: string; // YouTube Video ID
  title: string;
  channelName: string;
  duration: string; // e.g., "5:21"
  description: string;
  thumbnailUrl: string;
}

export interface SpokenPhrase {
  id: string;
  start: number; // in seconds
  end: number; // in seconds
  text: string;
  speaker?: string;
  confidence: number; // 0.0 to 1.0
  tags: { category: string; value: string }[];
}

export interface Sample {
  id: string; // Unique sample ID
  phrase_text: string;
  video_id: string;
  video_title: string;
  start_time: number;
  duration: number;
  file_path: string; // Local audio path or download API
  isolated_path?: string; // API path to isolated vocals track (set after vocal isolation completes)
  energy_score: number;
  is_processed: boolean;
  createdAt: string;
  tags?: Tag[];
}

export interface Tag {
  id: string;
  sample_id: string;
  category: string; // 'emotion', 'gender', 'role', 'character', etc.
  value: string;
}

export interface ProcessingOptions {
  voiceIsolation: boolean; // Demucs
  silenceTrimming: boolean; // Trim
  normalization: boolean; // Normalized loudness
  fadeInOut: boolean; // Fades (0.05s)
}

export interface JobStatus {
  id: string;
  video_id: string;
  video_title: string;
  phrase_text: string;
  start_time: number;
  end_time: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number; // 0 to 100
  message: string;
  options: ProcessingOptions;
  resultSampleId?: string;
  error?: string;
}

export interface PeakData {
  peaks: number[]; // Array of peak values normalized 0 to 1
  sampleRate: number;
}
