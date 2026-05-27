import os
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

import config

router = APIRouter(prefix="/outputs", tags=["Outputs"])

ALLOWED_OUTPUTS = {
    "novel_view.png", 
    "novel_depth.png", 
    "nerf_animation.gif",
    "coarse.pth",
    "fine.pth",
    "encoder.pth",
    "occupancy.pth"
}

@router.get("/{session_id}/{filename}")
def serve_output(session_id: str, filename: str):
    # Strict path validation prevents traversal
    if filename not in ALLOWED_OUTPUTS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested file.")
        
    file_path = os.path.join(config.SESSION_BASE_DIR, session_id, "outputs", filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output file not found or not generated yet.")
        
    return FileResponse(file_path)
