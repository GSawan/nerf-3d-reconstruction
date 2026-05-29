export interface SessionResponse {
  session_id: string;
  total_uploads: number;
  accepted_count: number;
  rejected_count: number;
  deduplicated_count: number;
  rejection_reasons: Record<string, number>;
  preprocessing_resolution: [number, number];
  aabb_scale: number;
  health_score?: number;
  mode?: string;
  image_truncation_count?: number;
}

export interface JobStatusResponse {
  session_id: string;
  status: string; // 'idle' | 'queued' | 'colmap_features' | 'colmap_matching' | 'colmap_sparse' | 'exporting' | 'completed' | 'failed'
  progress: number;
  logs: string[];
  error: string | null;
  model_url?: string | null;
  point_count?: number;
  camera_count?: number;
  // Legacy fields kept for backward compat
  epoch?: number;
  total_epochs?: number;
  loss?: number | null;
  psnr?: number | null;
  previews?: string[];
}
