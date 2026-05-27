import os
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status

import config
from services.preprocess import Preprocessor
from api.schemas.models import SessionResponse

router = APIRouter(prefix="/upload", tags=["Upload"])

@router.post("/", response_model=SessionResponse)
async def upload_dataset(files: List[UploadFile] = File(...)):
    if len(files) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Minimum 10 files required for reconstruction."
        )
        
    if len(files) > config.MAX_UPLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Maximum {config.MAX_UPLOADS} files exceeded."
        )

    # Validate file sizes before processing
    total_size = 0
    max_single_bytes = config.MAX_SINGLE_IMAGE_MB * 1024 * 1024
    max_total_bytes = config.MAX_TOTAL_UPLOAD_MB * 1024 * 1024

    for file in files:
        if file.size is not None:
            if file.size > max_single_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File {file.filename} exceeds max size of {config.MAX_SINGLE_IMAGE_MB}MB."
                )
            total_size += file.size
            
        # Validate format
        content_type = file.content_type or ""
        if not content_type.startswith("image/jpeg") and not content_type.startswith("image/png"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File {file.filename} is not a supported format. Only JPEG and PNG are allowed."
            )
            
    if total_size > max_total_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Total upload size exceeds {config.MAX_TOTAL_UPLOAD_MB}MB."
        )

    # Initialize Preprocessor (which generates the session ID and creates dataset directories)
    preprocessor = Preprocessor(base_dir="datasets")
    print(f"[API] Upload Route Hit! Starting session: {preprocessor.session_id}", flush=True)
    print(f"[API] Received {len(files)} files. Total Size: {total_size / (1024*1024):.2f} MB", flush=True)
    
    # Create raw_uploads directory for this session to store the initial uploads
    raw_dir = os.path.join(preprocessor.session_dir, "raw_uploads")
    os.makedirs(raw_dir, exist_ok=True)
    print(f"[API] Saving raw files to: {raw_dir}", flush=True)
    
    # Save files safely to raw directory
    saved_count = 0
    for file in files:
        safe_filename = os.path.basename(file.filename)
        file_path = os.path.join(raw_dir, safe_filename)
        
        with open(file_path, "wb") as f:
            f.write(await file.read())
        saved_count += 1
            
    print(f"[API] Successfully wrote {saved_count} files to disk.", flush=True)

    # Run preprocessing synchronously
    try:
        print(f"[API] Executing preprocessor.normalize_dataset()", flush=True)
        metadata = preprocessor.normalize_dataset()
        print(f"[API] Preprocessing complete. Metadata: {metadata}", flush=True)
        
        # Clean up raw_uploads to save space
        for file in os.listdir(raw_dir):
            os.remove(os.path.join(raw_dir, file))
        os.rmdir(raw_dir)
        print(f"[API] Cleaned up temporary raw directory.", flush=True)
        
        # Return response matching the schema
        return SessionResponse(
            session_id=metadata["session_id"],
            total_uploads=metadata["total_uploads"],
            accepted_count=metadata["accepted_count"],
            rejected_count=metadata["rejected_count"],
            deduplicated_count=0,
            rejection_reasons={},
            preprocessing_resolution=(0, 0),
            aabb_scale=1.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preprocessing pipeline failed: {str(e)}"
        )
