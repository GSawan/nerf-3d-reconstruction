import json
import os
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

import config

class JobState(str, Enum):
    QUEUED = "QUEUED"
    PREPROCESSING = "PREPROCESSING"
    TRAINING = "TRAINING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

@dataclass
class JobConfig:
    epochs: int = config.EPOCHS
    target_proc_res: tuple = config.TARGET_PROC_RES
    rays_per_batch: int = config.RAYS_PER_BATCH
    occ_warmup_epochs: int = config.OCC_WARMUP_EPOCHS
    video_frames: int = config.VIDEO_FRAMES

@dataclass
class JobProgress:
    epoch: int = 0
    total_epochs: int = 0
    loss: float = 0.0
    psnr: float = 0.0
    estimated_completion_pct: float = 0.0
    active_stage: str = "WAITING"
    queue_position: int = 0

@dataclass
class JobTiming:
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    preprocessing_duration: float = 0.0
    training_duration: float = 0.0
    rendering_duration: float = 0.0
    total_runtime: float = 0.0

@dataclass
class JobMetadata:
    session_id: str
    state: JobState = JobState.QUEUED
    config: JobConfig = field(default_factory=JobConfig)
    progress: JobProgress = field(default_factory=JobProgress)
    timing: JobTiming = field(default_factory=JobTiming)
    retry_count: int = 0
    max_retries: int = 1
    cancel_requested: bool = False
    error_message: Optional[str] = None
    
    def get_save_path(self):
        base_dir = os.path.join(config.SESSION_BASE_DIR, self.session_id, "metadata")
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, "job_state.json")

    def save(self):
        path = self.get_save_path()
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=4)

    @classmethod
    def load(cls, session_id: str):
        path = os.path.join(config.SESSION_BASE_DIR, session_id, "metadata", "job_state.json")
        if not os.path.exists(path):
            return cls(session_id=session_id)
            
        with open(path, "r") as f:
            data = json.load(f)
            
        # Reconstruct dataclasses
        data['state'] = JobState(data['state'])
        data['config'] = JobConfig(**data['config'])
        data['progress'] = JobProgress(**data['progress'])
        data['timing'] = JobTiming(**data['timing'])
        return cls(**data)
