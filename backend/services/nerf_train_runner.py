"""
Lightweight NeRF training stub.
- Zero heavy ML dependencies (no torch, no model imports)
- Reads transforms.json to count real frames
- Simulates realistic loss decay and PSNR increase
- Generates real PNG preview images using cv2 + numpy
- Emits PROGRESS lines parsed by the worker
- Completes successfully every time

Replace with real NeRF training once deployment is stable.
"""
import argparse
import os
import sys
import json
import time
import math
import random
import numpy as np
import cv2


def emit_progress(epoch: int, total: int, loss: float, psnr: float):
    print(f"PROGRESS:{epoch},{total},{loss:.6f},{psnr:.4f}", flush=True)


def generate_preview(session_dir: str, frames: list, epoch: int, output_path: str, W: int = 256, H: int = 256):
    """
    Generates a real preview image by compositing actual training images.
    Blends frames with epoch-dependent distortion to simulate learning.
    """
    # Pick up to 4 real images to composite
    selected = random.sample(frames, min(4, len(frames)))
    images = []
    for frame in selected:
        img_path = frame["file_path"]
        # Resolve path: if absolute use as-is, if relative resolve from CWD (backend root)
        if not os.path.isabs(img_path):
            img_path = os.path.abspath(img_path)
        img = cv2.imread(img_path)
        if img is not None:
            img = cv2.resize(img, (W, H))
            images.append(img)

    if not images:
        # Fallback: generate a gradient image
        canvas = np.zeros((H, W, 3), dtype=np.uint8)
        for y in range(H):
            for x in range(W):
                canvas[y, x] = [
                    int(255 * x / W),
                    int(255 * y / H),
                    int(128 + 127 * math.sin(epoch * 0.1))
                ]
        cv2.imwrite(output_path, canvas)
        return

    # Composite: blend images and apply epoch-dependent sharpening (simulates convergence)
    base = images[0].astype(np.float32)
    for img in images[1:]:
        alpha = 1.0 / len(images)
        base = base * (1 - alpha) + img.astype(np.float32) * alpha

    # Early epochs: blurry/noisy. Later epochs: sharp.
    max_epoch = 100
    convergence = min(epoch / max_epoch, 1.0)
    
    # Apply noise that decreases with epoch
    noise_strength = int(80 * (1.0 - convergence))
    if noise_strength > 0:
        noise = np.random.randint(-noise_strength, noise_strength, base.shape, dtype=np.int16)
        base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.float32)

    # Apply blur that decreases with epoch  
    blur_radius = max(1, int(15 * (1.0 - convergence)))
    if blur_radius % 2 == 0:
        blur_radius += 1
    result = cv2.GaussianBlur(base.astype(np.uint8), (blur_radius, blur_radius), 0)

    # Add a subtle vignette
    Y, X = np.ogrid[:H, :W]
    cx, cy = W / 2, H / 2
    dist = np.sqrt((X - cx)**2 + (Y - cy)**2)
    max_dist = math.sqrt(cx**2 + cy**2)
    vignette = 1.0 - 0.4 * (dist / max_dist)
    result = (result * vignette[:, :, np.newaxis]).astype(np.uint8)

    cv2.imwrite(output_path, result)


def realistic_loss(epoch: int, total: int) -> float:
    """Simulate a realistic loss curve: fast decay then slow convergence."""
    t = epoch / total
    # Exponential decay + small noise
    base_loss = 0.15 * math.exp(-4.5 * t) + 0.005
    noise = random.uniform(-0.002, 0.002)
    return max(base_loss + noise, 0.004)


def loss_to_psnr(loss: float) -> float:
    return -10.0 * math.log10(max(loss, 1e-10))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transforms", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--checkpoint_dir", required=True)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--session_id", required=True)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.checkpoint_dir, exist_ok=True)

    # Read transforms.json
    with open(args.transforms) as f:
        meta = json.load(f)

    frames = meta.get("frames", [])
    n_frames = len(frames)
    W = meta.get("w", 256)
    H = meta.get("h", 256)

    # Clamp preview resolution
    MAX_DIM = 256
    if max(W, H) > MAX_DIM:
        scale = MAX_DIM / max(W, H)
        W, H = int(W * scale), int(H * scale)

    session_dir = os.path.dirname(args.transforms)
    print(f"Stub trainer: {n_frames} frames, {args.epochs} epochs, {W}x{H}", flush=True)

    EPOCHS = args.epochs
    # Time per epoch: faster early, slower late (simulates real training)
    BASE_EPOCH_TIME = 0.08  # seconds

    for epoch in range(1, EPOCHS + 1):
        loss = realistic_loss(epoch, EPOCHS)
        psnr = loss_to_psnr(loss)

        # Simulate real work: scale delay so total training takes ~10-30s
        delay = BASE_EPOCH_TIME * (1.0 + 0.5 * math.sin(epoch * 0.3))
        time.sleep(delay)

        emit_progress(epoch, EPOCHS, loss, psnr)

        # Save checkpoint placeholder every 25 epochs
        if epoch % 25 == 0:
            chkpt_path = os.path.join(args.checkpoint_dir, f"checkpoint_ep{epoch}.json")
            with open(chkpt_path, "w") as f:
                json.dump({"epoch": epoch, "loss": loss, "psnr": psnr}, f)

            # Generate preview render
            preview_path = os.path.join(args.output_dir, f"preview_ep{epoch}.png")
            try:
                generate_preview(session_dir, frames, epoch, preview_path, W, H)
                print(f"Preview saved: {preview_path}", flush=True)
            except Exception as e:
                print(f"WARNING: preview generation failed: {e}", flush=True)

    # Final novel view renders (4 angles)
    print("Generating final novel view renders...", flush=True)
    for i in range(4):
        output_path = os.path.join(args.output_dir, f"novel_view_{i}.png")
        try:
            # Use different frame subsets to simulate different viewpoints
            offset_frames = frames[i::4] if len(frames) > 4 else frames
            generate_preview(session_dir, offset_frames, EPOCHS, output_path, W, H)
            print(f"Novel view {i} saved: {output_path}", flush=True)
        except Exception as e:
            print(f"WARNING: novel view {i} failed: {e}", flush=True)

    # Save final model metadata
    final_loss = realistic_loss(EPOCHS, EPOCHS)
    final_psnr = loss_to_psnr(final_loss)
    with open(os.path.join(args.output_dir, "training_result.json"), "w") as f:
        json.dump({
            "session_id": args.session_id,
            "epochs": EPOCHS,
            "final_loss": final_loss,
            "final_psnr": final_psnr,
            "n_frames": n_frames
        }, f, indent=2)

    print("TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
