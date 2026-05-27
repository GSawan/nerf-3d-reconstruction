"""
NeRF training runner — subprocess-based, session-aware.
Adapts the existing train.py to run against a specific session's transforms.json.
"""
import os
import sys
import json
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_nerf_training(
    session_id: str,
    session_dir: str,
    transforms_path: str,
    epochs: int = 150,
    on_progress=None  # Optional callback: fn(epoch, total, loss, psnr)
) -> dict:
    """
    Runs the NeRF training script as a subprocess, streaming progress via callback.
    Returns dict with final loss/psnr and output paths.
    """
    output_dir = os.path.join("outputs", session_id)
    checkpoint_dir = os.path.join(output_dir, "checkpoints")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(checkpoint_dir, exist_ok=True)

    backend_root = Path(__file__).parent.parent
    train_script = backend_root / "services" / "nerf_train_runner.py"

    cmd = [
        sys.executable, str(train_script),
        "--transforms", transforms_path,
        "--output_dir", output_dir,
        "--checkpoint_dir", checkpoint_dir,
        "--epochs", str(epochs),
        "--session_id", session_id
    ]

    logger.info(f"[TRAIN] Launching training subprocess: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(backend_root)
    )

    result = {"final_loss": None, "final_psnr": None, "output_dir": output_dir}

    for line in process.stdout:
        line = line.strip()
        if not line:
            continue

        logger.info(f"[TRAIN STDOUT] {line}")

        # Parse structured progress lines: PROGRESS:epoch,total,loss,psnr
        if line.startswith("PROGRESS:"):
            try:
                parts = line[len("PROGRESS:"):].split(",")
                epoch = int(parts[0])
                total = int(parts[1])
                loss = float(parts[2])
                psnr = float(parts[3])
                result["final_loss"] = loss
                result["final_psnr"] = psnr
                if on_progress:
                    on_progress(epoch, total, loss, psnr)
            except Exception:
                pass

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"Training subprocess exited with code {process.returncode}")

    return result
