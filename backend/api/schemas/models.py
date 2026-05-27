from pydantic import BaseModel
from typing import Dict, Optional, List

class SessionResponse(BaseModel):
    session_id: str
    total_uploads: int
    accepted_count: int
    rejected_count: int
    deduplicated_count: int
    rejection_reasons: Dict[str, int]
    preprocessing_resolution: tuple
    aabb_scale: float

class JobStartRequest(BaseModel):
    epochs: Optional[int] = None
    video_frames: Optional[int] = None

class JobOutputsStatus(BaseModel):
    novel_view: bool
    depth_map: bool
    video: bool
    
class JobStatusResponse(BaseModel):
    session_id: str
    state: str
    epoch: int
    total_epochs: int
    loss: float
    psnr: float
    estimated_completion_pct: float
    active_stage: str
    queue_position: int
    error_message: Optional[str]
    outputs: JobOutputsStatus

class HealthResponse(BaseModel):
    status: str
    gpu_available: bool
    queue_size: int
    active_job_count: int
