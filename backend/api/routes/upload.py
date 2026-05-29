import os
import uuid
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from pydantic import BaseModel

from services.preprocess import Preprocessor

router = APIRouter(prefix="/upload", tags=["Upload"])

# Supported image extensions (more permissive than MIME type check)
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

# Limits
MAX_UPLOADS = 300
MIN_UPLOADS = 5
MAX_SINGLE_IMAGE_MB = 30
MAX_TOTAL_UPLOAD_MB = 2048  # 2 GB


class SessionResponse(BaseModel):
    session_id: str
    total_uploads: int
    accepted_count: int
    rejected_count: int
    deduplicated_count: int
    rejection_reasons: dict
    preprocessing_resolution: list
    aabb_scale: float
    health_score: int = 100
    mode: str = "high"
    image_truncation_count: int = 0


@router.post("/", response_model=SessionResponse)
async def upload_dataset(files: List[UploadFile] = File(...)):
    """
    Accept image uploads. Saves and preprocesses them for COLMAP.
    """
    if not files or len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files received. Please select images to upload."
        )

    if len(files) < MIN_UPLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Need at least {MIN_UPLOADS} images for reconstruction. You uploaded {len(files)}."
        )

    if len(files) > MAX_UPLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_UPLOADS} images allowed. You uploaded {len(files)}."
        )

    # Validate files BEFORE reading all content
    max_single_bytes = MAX_SINGLE_IMAGE_MB * 1024 * 1024
    max_total_bytes = MAX_TOTAL_UPLOAD_MB * 1024 * 1024
    total_size = 0

    for file in files:
        # Check extension (more reliable than MIME type — browsers lie about content-type)
        filename = file.filename or ""
        ext = os.path.splitext(filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type: '{filename}'. Only JPEG, PNG, BMP, TIFF, WebP allowed."
            )

        # Check individual file size if available
        if file.size is not None and file.size > max_single_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' is {file.size // (1024*1024)}MB — max is {MAX_SINGLE_IMAGE_MB}MB."
            )

        if file.size is not None:
            total_size += file.size

    if total_size > max_total_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Total upload size exceeds {MAX_TOTAL_UPLOAD_MB}MB limit."
        )

    # Create session
    preprocessor = Preprocessor(base_dir="datasets")
    print(f"[UPLOAD] Session: {preprocessor.session_id} | {len(files)} files", flush=True)

    # Save raw uploads
    raw_dir = os.path.join(preprocessor.session_dir, "raw_uploads")
    os.makedirs(raw_dir, exist_ok=True)

    saved = 0
    for i, file in enumerate(files):
        try:
            # Generate safe filename to avoid path traversal
            ext = os.path.splitext((file.filename or "img").lower())[1]
            if ext not in ALLOWED_EXTENSIONS:
                ext = '.jpg'
            safe_name = f"upload_{i:04d}{ext}"
            file_path = os.path.join(raw_dir, safe_name)

            content = await file.read()
            if len(content) == 0:
                print(f"[UPLOAD] Skipping empty file: {file.filename}", flush=True)
                continue

            with open(file_path, "wb") as f:
                f.write(content)
            saved += 1
        except Exception as e:
            print(f"[UPLOAD] Error saving file {file.filename}: {e}", flush=True)
            # Continue — don't fail entire upload for one bad file

    if saved < MIN_UPLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {saved} valid images were saved. Need at least {MIN_UPLOADS}."
        )

    print(f"[UPLOAD] Saved {saved} files. Running preprocessor...", flush=True)

    # Run preprocessing (blur filter, resize, save to images/)
    try:
        metadata = preprocessor.normalize_dataset(mode="high")
        print(f"[UPLOAD] Preprocessing done: {metadata['accepted_count']} accepted.", flush=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image preprocessing failed: {str(e)}"
        )
    finally:
        # Always clean up raw uploads
        try:
            import shutil
            if os.path.exists(raw_dir):
                shutil.rmtree(raw_dir)
        except Exception:
            pass

    # Check we have enough images after preprocessing
    images_dir = preprocessor.images_dir
    final_count = len([
        f for f in os.listdir(images_dir)
        if os.path.splitext(f.lower())[1] in ALLOWED_EXTENSIONS
    ]) if os.path.exists(images_dir) else 0

    if final_count < MIN_UPLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"After quality filtering, only {final_count} images passed. "
                f"Need at least {MIN_UPLOADS}. "
                f"Please upload sharper, better-lit photos."
            )
        )

    return SessionResponse(
        session_id=metadata["session_id"],
        total_uploads=metadata["total_uploads"],
        accepted_count=metadata["accepted_count"],
        rejected_count=metadata["rejected_count"],
        deduplicated_count=0,
        rejection_reasons=metadata.get("rejection_reasons", {}),
        preprocessing_resolution=[0, 0],
        aabb_scale=1.0,
        health_score=metadata.get("health_score", 100),
        mode=metadata.get("mode", "high"),
        image_truncation_count=metadata.get("image_truncation_count", 0),
    )
