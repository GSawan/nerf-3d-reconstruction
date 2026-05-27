import torch
from fastapi import APIRouter
from api.schemas.models import HealthResponse
from services.orchestrator import get_job_manager

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/", response_model=HealthResponse)
def get_health():
    jm = get_job_manager()
    return HealthResponse(
        status="operational",
        gpu_available=torch.cuda.is_available(),
        queue_size=jm.job_queue.qsize(),
        active_job_count=len(jm.active_jobs)
    )
