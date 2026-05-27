"""
Full reconstruction + NeRF training worker.
Pipeline: COLMAP → transforms.json → NeRF training → preview renders
"""
import os
import logging
from datetime import datetime
from services.colmap_pipeline import ColmapPipeline
import shutil

# In-memory job state store
JOB_STATES = {}


def get_job_state(session_id: str):
    if session_id not in JOB_STATES:
        return {"status": "unknown", "progress": 0, "logs": [], "error": None,
                "epoch": 0, "total_epochs": 0, "loss": None, "psnr": None, "previews": []}
    return JOB_STATES[session_id]


def update_state(session_id: str, status: str, progress: int, log_msg: str = None,
                 error: str = None, epoch: int = None, total_epochs: int = None,
                 loss: float = None, psnr: float = None):
    if session_id not in JOB_STATES:
        JOB_STATES[session_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "epoch": 0, "total_epochs": 0, "loss": None, "psnr": None, "previews": []
        }

    state = JOB_STATES[session_id]
    state["status"] = status
    state["progress"] = progress

    if epoch is not None:
        state["epoch"] = epoch
    if total_epochs is not None:
        state["total_epochs"] = total_epochs
    if loss is not None:
        state["loss"] = loss
    if psnr is not None:
        state["psnr"] = psnr

    if log_msg:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{ts}] {log_msg}"
        state["logs"].append(formatted)
        logging.info(f"[JOB {session_id[:8]}] {log_msg}")

        log_file = os.path.join("datasets", session_id, "job_log.txt")
        try:
            with open(log_file, "a") as f:
                f.write(formatted + "\n")
        except Exception:
            pass

    if error:
        state["error"] = error


def add_preview(session_id: str, preview_url: str):
    if session_id in JOB_STATES:
        JOB_STATES[session_id]["previews"].append(preview_url)


def run_reconstruction(session_id: str, epochs: int = 100, mode: str = "mesh"):
    """
    Full pipeline: COLMAP → transforms.json → NeRF Training → Previews
    """
    try:
        session_dir = os.path.join("datasets", session_id)
        if not os.path.exists(session_dir):
            raise FileNotFoundError(f"Session directory not found: {session_dir}")

        # ── Phase 1: COLMAP Sparse ──────────────────────────────────────────────
        update_state(session_id, "sparse_reconstruction", 5, "Extracting features...")
        pipeline = ColmapPipeline(session_dir=session_dir)
        pipeline.extract_features()

        update_state(session_id, "sparse_reconstruction", 15, "Matching features...")
        pipeline.match_features()

        update_state(session_id, "sparse_reconstruction", 30, "Running sparse reconstruction (mapper)...")
        pipeline.reconstruct_sparse()
        
        update_state(session_id, "sparse_reconstruction", 32, "Analyzing sparse model...")
        analyzer_output = pipeline.analyze_model()
        
        reg_imgs_count = 0
        total_imgs_count = 1
        sparse_points_count = 0
        
        if analyzer_output:
            try:
                total_imgs_count = len([f for f in os.listdir(pipeline.images_dir) if os.path.isfile(os.path.join(pipeline.images_dir, f))])
            except Exception:
                pass
                
            for line in analyzer_output.split('\n'):
                line = line.strip()
                if "Registered images:" in line:
                    reg_imgs_count = int(line.split(":")[-1].strip())
                    update_state(session_id, "sparse_reconstruction", 33, f"Registered cameras: {reg_imgs_count} / {total_imgs_count}")
                elif "Points:" in line:
                    sparse_points_count = int(line.split(":")[-1].strip())
                    update_state(session_id, "sparse_reconstruction", 34, f"Sparse points: {sparse_points_count}")
        
        # QUALITY GATE
        registration_ratio = (reg_imgs_count / max(1, total_imgs_count)) * 100
        if registration_ratio < 20 or sparse_points_count < 500:
            error_msg = f"Insufficient reconstruction quality. Registered only {reg_imgs_count}/{total_imgs_count} cameras ({registration_ratio:.1f}%) and {sparse_points_count} sparse points. Minimum required is 20% registration and 500 points."
            update_state(session_id, "failed", 0, error_msg, error="Insufficient camera registration")
            return
            
        update_state(session_id, "sparse_reconstruction", 35, "Exporting sparse point cloud to PLY...")
        sparse_ply = pipeline.export_sparse_ply()
        
        if mode == "ngp":
            update_state(session_id, "transforms_generation", 37, "Generating transforms.json for Instant-NGP...")
            from services.colmap_to_nerf import convert
            sparse_0 = os.path.join(session_dir, "sparse", "0")
            images_dir = os.path.join(session_dir, "images")
            transforms_out = os.path.join(session_dir, "transforms.json")
            try:
                convert(sparse_0, images_dir, transforms_out)
                update_state(session_id, "transforms_generation", 39, "transforms.json successfully generated.")
            except Exception as e:
                error_msg = f"Failed to generate transforms.json: {str(e)}"
                update_state(session_id, "failed", 0, error_msg, error="Transforms generation failed")
                return

            update_state(session_id, "ngp_training", 40, "Launching Instant-NGP GUI Viewer...")
            
            from config import INSTANT_NGP_PATH
            import subprocess
            cmd = [INSTANT_NGP_PATH, "--scene", session_dir]
            logging.info(f"Launching NGP: {cmd}")
            subprocess.Popen(cmd)
            
            update_state(session_id, "viewer_ready", 100, "Instant-NGP window launched locally! Training is actively running in the native viewer.")
            return

        # ── Phase 2: Dense Stereo ──────────────────────────────────────────────
        update_state(session_id, "dense_reconstruction", 40, "Undistorting images for dense stereo...")
        pipeline.undistort_images()
        
        update_state(session_id, "dense_reconstruction", 50, "Running dense patch-match stereo...")
        pipeline.run_patch_match()
        
        update_state(session_id, "dense_reconstruction", 65, "Fusing dense depth maps into point cloud...")
        dense_ply = pipeline.run_stereo_fusion()
        
        # ── Phase 3: Poisson Surface Reconstruction ────────────────────────────
        update_state(session_id, "meshing", 80, "Generating Poisson surface mesh...")
        mesh_ply = pipeline.generate_mesh()
        
        # ── Artifact Export & Validation ───────────────────────────────────────
        update_state(session_id, "meshing", 90, "Validating generated artifacts and organizing output...")
        
        output_model_dir = os.path.join(session_dir, "model")
        os.makedirs(output_model_dir, exist_ok=True)
        
        valid_artifacts = []
        
        def is_valid_ply(filepath):
            if not filepath or not os.path.exists(filepath):
                return False
            if os.path.getsize(filepath) < 1024:  # Must be > 1KB
                return False
            return True
            
        if is_valid_ply(mesh_ply):
            shutil.copy2(mesh_ply, os.path.join(output_model_dir, "mesh.ply"))
            valid_artifacts.append("mesh.ply")
            
        if is_valid_ply(dense_ply):
            shutil.copy2(dense_ply, os.path.join(output_model_dir, "dense.ply"))
            valid_artifacts.append("dense.ply")
            
        if is_valid_ply(sparse_ply):
            shutil.copy2(sparse_ply, os.path.join(output_model_dir, "sparse.ply"))
            valid_artifacts.append("sparse.ply")
            
        if not valid_artifacts:
            update_state(session_id, "failed", 0, "All artifacts failed validation. Reconstruction collapsed.", error="Artifact generation failed")
            return
            
        # Select canonical model
        canonical_target = os.path.join(output_model_dir, "model.ply")
        if "mesh.ply" in valid_artifacts:
            shutil.copy2(os.path.join(output_model_dir, "mesh.ply"), canonical_target)
            msg = "Mesh generated successfully!"
        elif "dense.ply" in valid_artifacts:
            shutil.copy2(os.path.join(output_model_dir, "dense.ply"), canonical_target)
            msg = "Meshing failed, falling back to dense point cloud."
        else:
            shutil.copy2(os.path.join(output_model_dir, "sparse.ply"), canonical_target)
            msg = "Dense stereo failed, falling back to sparse point cloud."

        update_state(session_id, "completed", 100, f"Pipeline complete. {msg}")

    except Exception as e:
        update_state(session_id, "failed", 0, f"Pipeline failed: {str(e)}", error=str(e))
        logging.exception(f"[JOB {session_id[:8]}] Unhandled error:")
