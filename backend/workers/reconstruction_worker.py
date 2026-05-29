"""
Reconstruction worker.
Pipeline: Preprocess -> COLMAP Sparse -> Export PLY -> Done
No Nerfstudio. No external viewers. Output served directly to Three.js in the website.

COLMAP flag compatibility notes:
- Do NOT use --SiftExtraction.use_gpu or --SiftMatching.use_gpu
  These vary by COLMAP version and commonly fail on Windows builds.
- Keep commands minimal and compatible with COLMAP 3.x+
"""
import os
import sys
import logging
import shutil
import subprocess
from datetime import datetime

# In-memory job state store
JOB_STATES = {}


def _persist_success(session_id: str, ply_path: str, pt_count: int, cam_count: int, model_url: str):
    """
    Post-pipeline: upload PLY to S3 and save Model3D record to DB.
    Runs in a fire-and-forget fashion — does NOT block the reconstruction response.
    """
    try:
        # ── S3 Upload ────────────────────────────────────────────────
        from services.s3 import upload_file, get_s3_key_for_output, is_s3_enabled, S3_BUCKET
        s3_key = None
        if is_s3_enabled():
            s3_key = get_s3_key_for_output(session_id)
            ok = upload_file(ply_path, s3_key, content_type="application/octet-stream")
            if ok:
                logging.info(f"[S3] Uploaded PLY → s3://{S3_BUCKET}/{s3_key}")
            else:
                s3_key = None  # fallback to local

        # ── DB Persistence ───────────────────────────────────────────
        import asyncio
        from db.database import AsyncSessionLocal
        from db.models import ReconstructionSession, Model3D, ModelFormat, ReconstructionStatus
        from sqlalchemy import select

        async def _save():
            async with AsyncSessionLocal() as db:
                # Update session record
                result = await db.execute(
                    select(ReconstructionSession).where(ReconstructionSession.id == session_id)
                )
                sess = result.scalar_one_or_none()
                if sess:
                    sess.status = ReconstructionStatus.COMPLETED
                    sess.progress = 100
                    sess.completed_at = datetime.utcnow()
                    sess.camera_count = cam_count
                    sess.point_count = pt_count
                    if s3_key:
                        sess.s3_output_prefix = f"outputs/{session_id}/"

                    # Create Model3D record
                    ply_size = os.path.getsize(ply_path) if os.path.exists(ply_path) else 0
                    model = Model3D(
                        session_id=session_id,
                        format=ModelFormat.PLY,
                        s3_key=s3_key,
                        file_size_bytes=ply_size,
                        point_count=pt_count,
                        camera_count=cam_count,
                        local_url=model_url,
                    )
                    db.add(model)
                    await db.commit()
                    logging.info(f"[DB] Session {session_id[:8]} persisted as COMPLETED")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_save())
            else:
                loop.run_until_complete(_save())
        except RuntimeError:
            asyncio.run(_save())

    except Exception as e:
        logging.warning(f"[POST-PIPELINE] Non-critical persist error: {e}")


def _persist_failure(session_id: str, error_msg: str):
    """Record pipeline failure in the DB. Non-blocking."""
    try:
        import asyncio
        from db.database import AsyncSessionLocal
        from db.models import ReconstructionSession, ReconstructionStatus
        from sqlalchemy import select

        async def _save():
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ReconstructionSession).where(ReconstructionSession.id == session_id)
                )
                sess = result.scalar_one_or_none()
                if sess:
                    sess.status = ReconstructionStatus.FAILED
                    sess.error_message = error_msg[:2000]
                    sess.completed_at = datetime.utcnow()
                    await db.commit()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_save())
            else:
                loop.run_until_complete(_save())
        except RuntimeError:
            asyncio.run(_save())
    except Exception as e:
        logging.warning(f"[POST-PIPELINE] Non-critical failure persist error: {e}")

# COLMAP executable path — tries env var first, falls back to known path
COLMAP_EXE = os.environ.get("COLMAP_PATH", r"C:\Users\Sawan\Downloads\COLMAP\COLMAP.bat")

# Supported image extensions
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}


# ─────────────────────────────────────────────────────────────────────────────
# State Management
# ─────────────────────────────────────────────────────────────────────────────

def get_job_state(session_id: str):
    if session_id not in JOB_STATES:
        return {
            "status": "unknown", "progress": 0, "logs": [],
            "error": None, "model_url": None, "point_count": 0, "camera_count": 0
        }
    return JOB_STATES[session_id]


def update_state(session_id: str, status: str, progress: int, log_msg: str = None,
                 error: str = None, model_url: str = None,
                 point_count: int = None, camera_count: int = None):
    """Thread-safe state update. Pass status=None to keep existing status."""
    if session_id not in JOB_STATES:
        JOB_STATES[session_id] = {
            "status": "queued", "progress": 0, "logs": [],
            "error": None, "model_url": None, "point_count": 0, "camera_count": 0
        }

    state = JOB_STATES[session_id]

    # Only update status if provided
    if status is not None:
        state["status"] = status

    # Only update progress if it's a real value (not -1 sentinel)
    if progress >= 0:
        state["progress"] = progress

    if model_url is not None:
        state["model_url"] = model_url
    if point_count is not None:
        state["point_count"] = point_count
    if camera_count is not None:
        state["camera_count"] = camera_count
    if error:
        state["error"] = error

    if log_msg:
        # Strip any non-ASCII characters to avoid Windows CP1252 encoding errors
        safe_msg = log_msg.encode('ascii', errors='replace').decode('ascii')
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{ts}] {safe_msg}"
        state["logs"].append(formatted)

        # Print to console (safe)
        try:
            print(f"[JOB {session_id[:8]}] {safe_msg}", flush=True)
        except Exception:
            pass

        # Write to disk log
        log_file = os.path.join("datasets", session_id, "job_log.txt")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# COLMAP Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_colmap(cmd: str, step_name: str, session_id: str, timeout: int = 3600) -> str:
    """
    Run a COLMAP command via subprocess.
    Returns stdout string on success. Raises Exception on failure.
    """
    logging.info(f"COLMAP CMD [{step_name}]: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",   # Replace undecodable chars — prevents crash on COLMAP output
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1"}
        )
        # Log last few lines of COLMAP output
        lines = [l.strip() for l in result.stdout.split('\n') if l.strip()]
        for line in lines[-5:]:
            update_state(session_id, None, -1, f"  [colmap] {line}")
        return result.stdout

    except subprocess.CalledProcessError as e:
        # Get last 800 chars of output for error context
        output = (e.stdout or "")[-800:].strip()
        raise Exception(f"COLMAP {step_name} failed (code {e.returncode}):\n{output}")

    except subprocess.TimeoutExpired:
        raise Exception(
            f"COLMAP {step_name} timed out after {timeout // 60} minutes. "
            f"Try with fewer images."
        )


def _find_sparse_model(sparse_dir: str) -> str:
    """
    Find the largest/best sparse reconstruction output folder.
    COLMAP mapper outputs sparse/0, sparse/1, etc.
    Returns path to best model dir, or None if not found.
    """
    if not os.path.exists(sparse_dir):
        return None

    # Look for numbered subdirectories (0, 1, 2 ...)
    candidates = []
    for name in os.listdir(sparse_dir):
        sub = os.path.join(sparse_dir, name)
        if os.path.isdir(sub) and name.isdigit():
            # Count points from points3D.bin or points3D.txt
            size = 0
            for pfile in ['points3D.bin', 'points3D.txt']:
                ppath = os.path.join(sub, pfile)
                if os.path.exists(ppath):
                    size = os.path.getsize(ppath)
                    break
            candidates.append((size, sub))

    if not candidates:
        return None

    # Return the one with the largest points file (most complete reconstruction)
    candidates.sort(reverse=True)
    return candidates[0][1]


def _count_images(images_dir: str) -> list:
    """Return list of image filenames in a directory."""
    if not os.path.exists(images_dir):
        return []
    return [
        f for f in os.listdir(images_dir)
        if os.path.splitext(f.lower())[1] in IMG_EXTS
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_reconstruction(session_id: str):
    """
    Full pipeline:
      1. Validate uploaded images
      2. COLMAP feature_extractor (CPU, no GPU flags = universal compatibility)
      3. COLMAP exhaustive_matcher
      4. COLMAP mapper (sparse reconstruction)
      5. Export PLY point cloud
      6. Serve to Three.js viewer in the website
    """
    session_dir = os.path.join("datasets", session_id)
    images_dir = os.path.join(session_dir, "images")
    sparse_dir = os.path.join(session_dir, "sparse")
    database_path = os.path.join(session_dir, "database.db")
    output_dir = os.path.join("outputs", session_id)

    try:
        # ── Pre-flight ────────────────────────────────────────────────────
        os.makedirs(sparse_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        if not os.path.exists(session_dir):
            raise FileNotFoundError(
                f"Session directory not found: {session_dir}. "
                f"Please upload images again."
            )

        images = _count_images(images_dir)
        if len(images) < 5:
            raise ValueError(
                f"Only {len(images)} image(s) found in session. "
                f"Need at least 5 images for reconstruction. "
                f"Please upload more overlapping photos of your object."
            )

        update_state(session_id, "colmap_features", 5,
                     f"Pipeline starting with {len(images)} images.")

        # Verify COLMAP executable exists
        colmap_path = COLMAP_EXE
        # If it's a .bat file, verify it exists
        if colmap_path.endswith('.bat') and not os.path.exists(colmap_path):
            # Try to find colmap in PATH
            result = subprocess.run(
                "where colmap", shell=True, capture_output=True, text=True
            )
            if result.returncode == 0:
                colmap_path = result.stdout.strip().split('\n')[0]
            else:
                raise FileNotFoundError(
                    f"COLMAP not found at '{COLMAP_EXE}' and not in PATH. "
                    f"Please install COLMAP or set COLMAP_PATH environment variable."
                )

        # ── Step 1: Feature Extraction ────────────────────────────────────
        update_state(session_id, "colmap_features", 10,
                     "Step 1/4: Extracting SIFT features from images...")

        # Remove stale database from previous runs
        if os.path.exists(database_path):
            os.remove(database_path)
            update_state(session_id, None, -1, "Cleared previous database.")

        # NOTE: Do NOT use --SiftExtraction.use_gpu or --FeatureExtraction.use_gpu
        # These flags are version-specific and commonly fail on Windows COLMAP builds.
        # COLMAP auto-detects GPU. For max compatibility we omit GPU flags entirely.
        cmd = (
            f'"{colmap_path}" feature_extractor '
            f'--database_path "{database_path}" '
            f'--image_path "{images_dir}" '
            f'--ImageReader.camera_model SIMPLE_RADIAL '
            f'--ImageReader.single_camera 1'
        )
        _run_colmap(cmd, "feature_extractor", session_id, timeout=1800)
        update_state(session_id, "colmap_matching", 28,
                     "Step 1/4 done: Features extracted from all images.")

        # ── Step 2: Feature Matching ──────────────────────────────────────
        update_state(session_id, "colmap_matching", 32,
                     "Step 2/4: Matching features across all image pairs...")

        # For <= 50 images: exhaustive_matcher (most reliable)
        # For > 50 images: vocab_tree_matcher would be faster but needs a vocab tree file
        # We'll stick with exhaustive for reliability
        cmd = (
            f'"{colmap_path}" exhaustive_matcher '
            f'--database_path "{database_path}"'
        )
        _run_colmap(cmd, "exhaustive_matcher", session_id, timeout=1800)
        update_state(session_id, "colmap_sparse", 52,
                     "Step 2/4 done: Feature matching complete.")

        # ── Step 3: Sparse Reconstruction (Mapper) ────────────────────────
        update_state(session_id, "colmap_sparse", 56,
                     "Step 3/4: Running COLMAP mapper (this takes 1-5 minutes)...")

        cmd = (
            f'"{colmap_path}" mapper '
            f'--database_path "{database_path}" '
            f'--image_path "{images_dir}" '
            f'--output_path "{sparse_dir}" '
            f'--Mapper.num_threads 4 '
            f'--Mapper.init_min_tri_angle 4'
        )
        _run_colmap(cmd, "mapper", session_id, timeout=3600)
        update_state(session_id, "colmap_sparse", 72,
                     "Step 3/4 done: Sparse 3D reconstruction complete.")

        # ── Find best model ───────────────────────────────────────────────
        best_model = _find_sparse_model(sparse_dir)
        if best_model is None:
            raise Exception(
                "COLMAP mapper ran but produced NO reconstruction. "
                "Common causes: "
                "(1) Not enough image overlap — walk around the object slowly. "
                "(2) Images too blurry or dark. "
                "(3) Object has very uniform/plain texture (glass, white walls). "
                "Try capturing 30-50 photos at different angles with good lighting."
            )

        update_state(session_id, "colmap_sparse", 73,
                     f"Found sparse model at: {os.path.basename(best_model)}")

        # ── Analyze model stats ───────────────────────────────────────────
        cam_count = 0
        pt_count = 0
        try:
            analyze_out = _run_colmap(
                f'"{colmap_path}" model_analyzer --path "{best_model}"',
                "model_analyzer", session_id, timeout=120
            )
            for line in analyze_out.split('\n'):
                line = line.strip()
                if 'Registered images:' in line:
                    try:
                        cam_count = int(line.split(':')[-1].strip())
                    except ValueError:
                        pass
                elif 'Points:' in line and ':' in line:
                    try:
                        pt_count = int(line.split(':')[-1].strip())
                    except ValueError:
                        pass
            update_state(session_id, "colmap_sparse", 76,
                         f"Cameras registered: {cam_count}/{len(images)} | 3D points: {pt_count}",
                         camera_count=cam_count, point_count=pt_count)
        except Exception as e:
            # Model analysis is optional
            update_state(session_id, None, -1,
                         f"Model analysis skipped (non-critical): {str(e)[:100]}")

        # Warn if registration ratio is poor but don't fail
        if cam_count > 0 and cam_count < len(images) * 0.5:
            update_state(session_id, None, -1,
                         f"WARNING: Only {cam_count}/{len(images)} cameras registered. "
                         f"Result may be incomplete. Consider re-capturing with more overlap.")

        # ── Step 4: Export PLY ────────────────────────────────────────────
        update_state(session_id, "exporting", 80,
                     "Step 4/4: Exporting 3D point cloud to PLY format...")

        # Use a safe output path (no spaces issue with quotes in the cmd)
        ply_path = os.path.join(best_model, "sparse.ply")
        cmd = (
            f'"{colmap_path}" model_converter '
            f'--input_path "{best_model}" '
            f'--output_path "{ply_path}" '
            f'--output_type PLY'
        )
        _run_colmap(cmd, "model_converter", session_id, timeout=300)

        if not os.path.exists(ply_path):
            raise Exception(
                "PLY export failed: sparse.ply was not created by model_converter. "
                "Check if COLMAP has write permissions to the output directory."
            )

        ply_size_bytes = os.path.getsize(ply_path)
        if ply_size_bytes < 100:
            raise Exception(
                f"PLY file is too small ({ply_size_bytes} bytes) — likely empty or corrupt. "
                f"The reconstruction may have produced 0 3D points."
            )

        # Copy PLY to outputs directory (served as static file by FastAPI)
        final_ply = os.path.join(output_dir, "model.ply")
        shutil.copy2(ply_path, final_ply)
        ply_size_kb = ply_size_bytes // 1024
        update_state(session_id, "exporting", 95,
                     f"Point cloud exported: {ply_size_kb} KB ({pt_count} points)")

        # ── Done ──────────────────────────────────────────────────────────
        model_url = f"/api/v1/outputs/{session_id}/model.ply"
        update_state(session_id, "completed", 100,
                     "RECONSTRUCTION COMPLETE! 3D model is ready. View it below.",
                     model_url=model_url)

        logging.info(f"[JOB {session_id[:8]}] SUCCESS - {final_ply} ({ply_size_kb} KB)")

        # Persist to DB + S3 (non-blocking, best-effort)
        _persist_success(session_id, final_ply, pt_count, cam_count, model_url)

    except Exception as e:
        err_msg = str(e)
        # Strip non-ASCII from error message too
        safe_err = err_msg.encode('ascii', errors='replace').decode('ascii')
        update_state(
            session_id, "failed", 0,
            f"PIPELINE FAILED: {safe_err}",
            error=safe_err
        )
        logging.exception(f"[JOB {session_id[:8]}] Unhandled error in pipeline:")

        # Persist failure to DB (non-blocking, best-effort)
        _persist_failure(session_id, safe_err)
