from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["Health"])

class HealthResponse(BaseModel):
    status: str
    gpu_available: bool = False
    message: str = ""

@router.get("/", response_model=HealthResponse)
def get_health():
    try:
        import torch
        gpu = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu else "none"
        return HealthResponse(
            status="operational",
            gpu_available=gpu,
            message=f"GPU: {gpu_name}" if gpu else "No GPU detected"
        )
    except Exception as e:
        return HealthResponse(
            status="operational",
            gpu_available=False,
            message=f"torch not available: {str(e)}"
        )
