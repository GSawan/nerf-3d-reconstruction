from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import re
from workers.reconstruction_worker import run_reconstruction, get_job_state, update_state

def is_valid_uuid(val: str) -> bool:
    return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", val))

router = APIRouter(prefix="/reconstruct", tags=["Reconstruction"])


class JobStatusResponse(BaseModel):
    session_id: str
    status: str
    progress: int
    logs: List[str]
    error: Optional[str] = None
    epoch: int = 0
    total_epochs: int = 0
    loss: Optional[float] = None
    psnr: Optional[float] = None
    previews: List[str] = []


class StartJobRequest(BaseModel):
    epochs: int = 100


@router.post("/{session_id}", response_model=JobStatusResponse)
async def start_reconstruction(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: StartJobRequest = StartJobRequest()
):
    """Starts the full reconstruction pipeline: COLMAP → NeRF Training → Renders."""
    if not is_valid_uuid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format.")
        
    state = get_job_state(session_id)
    active_states = ["queued", "sparse_reconstruction", "dense_reconstruction", "meshing"]
    if state["status"] in active_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job already active for session {session_id} (status: {state['status']})"
        )

    update_state(session_id, "queued", 0, "Job added to queue.")
    background_tasks.add_task(run_reconstruction, session_id, body.epochs)

    return JobStatusResponse(
        session_id=session_id, status="queued", progress=0,
        logs=["Job added to queue."], error=None
    )


@router.get("/status/{session_id}", response_model=JobStatusResponse)
async def get_reconstruction_status(session_id: str):
    """Polls the live status and training metrics for a session."""
    if not is_valid_uuid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format.")
        
    state = get_job_state(session_id)
    # Return idle state instead of 404 — prevents frontend polling crashes
    # on race conditions or after server restarts
    return JobStatusResponse(
        session_id=session_id,
        status=state["status"] if state["status"] != "unknown" else "idle",
        progress=state["progress"],
        logs=state["logs"],
        error=state["error"],
        epoch=state.get("epoch", 0),
        total_epochs=state.get("total_epochs", 0),
        loss=state.get("loss"),
        psnr=state.get("psnr"),
        previews=state.get("previews", [])
    )


@router.get("/outputs/{session_id}/{filename}")
async def get_output_file(session_id: str, filename: str):
    """Serves rendered preview images."""
    if not is_valid_uuid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format.")
        
    # Prevent path traversal
    safe_filename = os.path.basename(filename)
    path = os.path.join("outputs", session_id, safe_filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(path)
