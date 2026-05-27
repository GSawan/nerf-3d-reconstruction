import os
from fastapi import APIRouter, HTTPException, status

import uuid
from typing import List
from fastapi import APIRouter, HTTPException, status

import config
from utils.jobs.models import JobConfig, JobState
from api.schemas.models import JobStartRequest, JobStatusResponse, JobOutputsStatus
from services.orchestrator import get_job_manager

router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.post("/{session_id}/start", response_model=JobStatusResponse)
def start_job(session_id: str, request: JobStartRequest = None):
    # Verify session exists
    session_dir = os.path.join(config.SESSION_BASE_DIR, session_id)
    if not os.path.exists(session_dir):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        
    jm = get_job_manager()
    
    # Check if already active
    meta_path = os.path.join(config.SESSION_BASE_DIR, session_id, "metadata", "job_state.json")
    if os.path.exists(meta_path) or session_id in jm.active_jobs:
        current_status = jm.get_job_status(session_id)
        if current_status.state in [JobState.QUEUED, JobState.TRAINING, JobState.RENDERING]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=f"Job is already active in state: {current_status.state}"
            )
        
    # Build config
    job_cfg = JobConfig()
    if request:
        if request.epochs is not None: job_cfg.epochs = request.epochs
        if request.video_frames is not None: job_cfg.video_frames = request.video_frames
        
    meta = jm.submit_job(session_id, job_cfg)
    return _build_status_response(meta)

@router.post("/{session_id}/cancel")
def cancel_job(session_id: str):
    jm = get_job_manager()
    jm.cancel_job(session_id)
    return {"status": "Cancellation requested"}

@router.get("/{session_id}/status", response_model=JobStatusResponse)
def get_job_status(session_id: str):
    jm = get_job_manager()
    meta = jm.get_job_status(session_id)
    return _build_status_response(meta)

def _build_status_response(meta) -> JobStatusResponse:
    # Check output availability dynamically
    outputs_dir = os.path.join(config.SESSION_BASE_DIR, meta.session_id, "outputs")
    outputs_status = JobOutputsStatus(
        novel_view=os.path.exists(os.path.join(outputs_dir, "novel_view.png")),
        depth_map=os.path.exists(os.path.join(outputs_dir, "novel_depth.png")),
        video=os.path.exists(os.path.join(outputs_dir, "nerf_animation.gif"))
    )
    
    return JobStatusResponse(
        session_id=meta.session_id,
        state=meta.state.value,
        epoch=meta.progress.epoch,
        total_epochs=meta.progress.total_epochs,
        loss=meta.progress.loss,
        psnr=meta.progress.psnr,
        estimated_completion_pct=meta.progress.estimated_completion_pct,
        active_stage=meta.progress.active_stage,
        queue_position=meta.progress.queue_position,
        error_message=meta.error_message,
        outputs=outputs_status
    )
