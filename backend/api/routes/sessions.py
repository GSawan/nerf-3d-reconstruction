import os
import shutil
import json
from fastapi import APIRouter, HTTPException, status
from typing import List, Dict

import config
from api.schemas.models import SessionResponse
from utils.ingest.session import SessionManager
from services.orchestrator import get_job_manager
from utils.jobs.models import JobState

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("/")
def list_sessions() -> List[str]:
    if not os.path.exists(config.SESSION_BASE_DIR):
        return []
    return [d for d in os.listdir(config.SESSION_BASE_DIR) 
            if os.path.isdir(os.path.join(config.SESSION_BASE_DIR, d))]

@router.get("/{session_id}")
def get_session_metadata(session_id: str) -> Dict:
    meta_path = os.path.join(config.SESSION_BASE_DIR, session_id, "metadata", "session_metadata.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metadata not found.")
        
    with open(meta_path, "r") as f:
        return json.load(f)

@router.delete("/{session_id}")
def delete_session(session_id: str):
    jm = get_job_manager()
    job_status = jm.get_job_status(session_id)
    
    # Protected deletion wrapper
    if job_status.state in [JobState.QUEUED, JobState.TRAINING, JobState.RENDERING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Cannot delete a session while a job is actively running or queued."
        )
        
    session_dir = os.path.join(config.SESSION_BASE_DIR, session_id)
    if os.path.exists(session_dir):
        shutil.rmtree(session_dir)
        return {"status": "Session deleted safely."}
    
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
