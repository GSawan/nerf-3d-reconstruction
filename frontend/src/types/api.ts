export interface SessionResponse {
  session_id: string;
  total_uploads: number;
  accepted_count: number;
  rejected_count: number;
  deduplicated_count: number;
  rejection_reasons: Record<string, number>;
  preprocessing_resolution: [number, number];
  aabb_scale: number;
}

export interface JobStatusResponse {
  session_id: string;
  status: string; // 'queued' | 'colmap' | 'converting' | 'training' | 'rendering' | 'completed' | 'failed'
  progress: number;
  logs: string[];
  error: string | null;
  epoch: number;
  total_epochs: number;
  loss: number | null;
  psnr: number | null;
  previews: string[];
}

