import os
import json
import time
import threading
import gc

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import cv2
import imageio.v2 as imageio
import matplotlib.pyplot as plt

from models.nerf import NeRF, HashEncoder, DirectionEncoder
from models.occupancy import OccupancyGrid
from utils.rays import get_rays
from utils.render import render_rays, render_image
from utils.jobs.models import JobConfig, JobProgress

import config

def load_image_rgb_white_bg(image_path: str) -> np.ndarray:
    image = imageio.imread(image_path)
    image = image.astype(np.float32) / 255.0

    if image.ndim == 2:
        image = np.stack([image, image, image], axis=-1)

    if image.shape[-1] == 4:
        rgb = image[..., :3]
        alpha = image[..., 3:4]
        image = rgb * alpha + (1.0 - alpha)

    return np.clip(image, 0.0, 1.0).astype(np.float32)


def run_reconstruction(
    session_id: str,
    job_config: JobConfig,
    progress_cb, 
    cancel_event: threading.Event
):
    """
    Executes the full pipeline (training, view render, video render) for a specific session.
    """
    
    device = torch.device(config.DEVICE)
    session_dir = os.path.join(config.SESSION_BASE_DIR, session_id)
    processed_dir = os.path.join(session_dir, "processed")
    outputs_dir = os.path.join(session_dir, "outputs")
    
    transforms_path = os.path.join(session_dir, "transforms.json")
    if not os.path.exists(transforms_path):
        raise FileNotFoundError(f"Missing transforms.json in {session_dir}")

    with open(transforms_path, "r") as f:
        meta = json.load(f)

    # Initialize models
    encoder_xyz = HashEncoder().to(device)
    encoder_dir = DirectionEncoder(num_freqs=config.DIR_FREQS).to(device)
    occupancy_grid = OccupancyGrid(
        resolution=config.OCC_GRID_RES, threshold=config.OCC_THRESHOLD, decay=config.OCC_DECAY
    ).to(device)

    model_coarse = NeRF().to(device)
    model_fine = NeRF().to(device)

    optimizer = optim.Adam(
        list(model_coarse.parameters()) + list(model_fine.parameters()) + 
        list(encoder_xyz.parameters()) + list(encoder_dir.parameters()),
        lr=config.LEARNING_RATE,
    )
    criterion = nn.MSELoss()
    amp_enabled = device.type == "cuda"
    scaler = torch.amp.GradScaler('cuda', enabled=amp_enabled)

    frames = meta["frames"]
    train_views = len(frames)
    
    if train_views == 0:
        raise ValueError("No frames found in transforms.json")
        
    camera_angle_x = float(meta.get("camera_angle_x", 0.6911))
    W, H = job_config.target_proc_res
    focal = float(0.5 * W / np.tan(0.5 * camera_angle_x))

    # Pre-load all images for tiny datasets, or stream them.
    # For RTX 3050, streaming is safer if N > 100. We will load on the fly.
    
    current_ray_batch = float(job_config.rays_per_batch)
    points_per_ray = config.N_SAMPLES_COARSE + config.N_SAMPLES_FINE
    
    progress = JobProgress(
        total_epochs=job_config.epochs,
        active_stage="TRAINING",
        estimated_completion_pct=0.0
    )
    progress_cb(progress)

    # TRAINING STAGE
    print(f"[Runner] Starting training loop ({job_config.epochs} epochs)...", flush=True)
    t0_train = time.time()
    for epoch in range(job_config.epochs):
        if cancel_event.is_set():
            progress.active_stage = "CANCELLED"
            progress_cb(progress)
            return

        epoch_skipped = 0
        epoch_total_pts = 0
        total_loss_tensor = torch.zeros(1, device=device)

        if epoch >= job_config.occ_warmup_epochs and epoch % config.OCC_UPDATE_EVERY == 0:
            occupancy_grid.update(model_coarse, encoder_xyz, encoder_xyz.bounds_min, encoder_xyz.bounds_max)
            
        active_occupancy_grid = occupancy_grid if epoch >= job_config.occ_warmup_epochs else None

        for frame in frames:
            if cancel_event.is_set():
                return
                
            img_path = os.path.join(processed_dir, frame["file_path"])
            if not os.path.exists(img_path): img_path += ".png"
            
            image_np = load_image_rgb_white_bg(img_path)
            target_image = torch.from_numpy(image_np).to(device=device, dtype=torch.float32)

            c2w = torch.tensor(frame["transform_matrix"], dtype=torch.float32, device=device)
            rays_o, rays_d = get_rays(H, W, focal, c2w)
            rays_o = rays_o.reshape(-1, 3).contiguous()
            rays_d = rays_d.reshape(-1, 3).contiguous()
            target_flat = target_image.reshape(-1, 3).contiguous()

            batch_size = min(int(current_ray_batch), rays_o.shape[0])
            ray_idx = torch.randperm(rays_o.shape[0], device=device)[:batch_size]
            
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast('cuda', enabled=amp_enabled):
                rgb_c, depth_c, rgb_f, depth_f, skipped, total_pts = render_rays(
                    model_coarse, model_fine, encoder_xyz, encoder_dir,
                    rays_o[ray_idx], rays_d[ray_idx],
                    config.N_SAMPLES_COARSE, config.N_SAMPLES_FINE,
                    config.NEAR, config.FAR, config.CHUNK_SIZE, True, active_occupancy_grid
                )
                
                epoch_skipped += skipped
                epoch_total_pts += total_pts
                
                # Dynamic scaling
                if skipped > 0 and total_pts > 0:
                    active_ratio = (total_pts - skipped) / total_pts
                    target_rays_sparse = config.TARGET_ACTIVE_SAMPLES / (points_per_ray * max(active_ratio, 0.05))
                    current_ray_batch = min(target_rays_sparse, current_ray_batch * 1.15, config.MAX_RAYS_PER_BATCH)
                    current_ray_batch = max(current_ray_batch, config.TARGET_ACTIVE_SAMPLES / points_per_ray, current_ray_batch * 0.85)

                loss = criterion(rgb_f, target_flat[ray_idx]) + 0.1 * criterion(rgb_c, target_flat[ray_idx])

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            
            total_loss_tensor += loss.detach()
            
            del target_image, rays_o, rays_d, target_flat, rgb_c, rgb_f, depth_c, depth_f, loss
            
        avg_loss = total_loss_tensor.item() / train_views
        safe_loss = max(avg_loss, 1e-10)
        psnr = -10.0 * np.log10(safe_loss)

        # Update progress
        progress.epoch = epoch + 1
        progress.loss = avg_loss
        progress.psnr = psnr
        # Training is roughly 80% of total pipeline time
        progress.estimated_completion_pct = ((epoch + 1) / job_config.epochs) * 80.0
        progress_cb(progress)
        
        # Save checkpoints safely
        if (epoch + 1) % config.CHECKPOINT_EVERY == 0:
            torch.save(model_coarse.state_dict(), os.path.join(outputs_dir, "coarse.pth"))
            torch.save(model_fine.state_dict(), os.path.join(outputs_dir, "fine.pth"))
            torch.save(encoder_xyz.state_dict(), os.path.join(outputs_dir, "encoder.pth"))
            torch.save(occupancy_grid.state_dict(), os.path.join(outputs_dir, "occupancy.pth"))

    # Force garbage collection post training
    print(f"[Runner] Training phase finished. Starting cleanup.", flush=True)
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()

    # RENDERING NOVEL VIEW
    if cancel_event.is_set(): return
    print(f"[Runner] Starting novel view rendering...", flush=True)
    progress.active_stage = "RENDERING_VIEW"
    progress_cb(progress)
    
    model_coarse.eval()
    model_fine.eval()
    
    # Synthetic novel view camera
    from utils.ingest.camera import generate_orbital_pose
    c2w_novel = torch.tensor(generate_orbital_pose(config.NOVEL_VIEW_THETA, config.NOVEL_VIEW_PHI, config.NOVEL_VIEW_RADIUS), dtype=torch.float32, device=device)
    
    with torch.inference_mode(), torch.amp.autocast('cuda', enabled=amp_enabled):
        rendered_rgb, depth_map = render_image(
            model_coarse, model_fine, encoder_xyz, encoder_dir,
            H, W, focal, c2w_novel, config.N_SAMPLES_COARSE, config.N_SAMPLES_FINE,
            config.NEAR, config.FAR, config.CHUNK_SIZE, config.MAX_RAYS_PER_BATCH, occupancy_grid
        )
        
    img_out = np.clip(rendered_rgb.cpu().numpy(), 0.0, 1.0)
    imageio.imwrite(os.path.join(outputs_dir, "novel_view.png"), (img_out * 255).astype(np.uint8))
    
    depth_out = depth_map.cpu().numpy()
    depth_out = (depth_out - depth_out.min()) / (depth_out.max() - depth_out.min() + 1e-8)
    plt.imsave(os.path.join(outputs_dir, "novel_depth.png"), depth_out, cmap="inferno")

    print(f"[Runner] Novel view successfully rendered and saved.", flush=True)

    progress.estimated_completion_pct = 90.0
    progress_cb(progress)

    # RENDERING VIDEO
    if cancel_event.is_set(): return
    progress.active_stage = "RENDERING_VIDEO"
    progress_cb(progress)

    frames_video = []
    with torch.inference_mode(), torch.amp.autocast('cuda', enabled=amp_enabled):
        for i in range(job_config.video_frames):
            if cancel_event.is_set(): return
            theta = 360.0 * i / job_config.video_frames
            c2w_vid = torch.tensor(generate_orbital_pose(theta, config.NOVEL_VIEW_PHI, config.NOVEL_VIEW_RADIUS), dtype=torch.float32, device=device)
            
            rgb, _ = render_image(
                model_coarse, model_fine, encoder_xyz, encoder_dir,
                H, W, focal, c2w_vid, config.N_SAMPLES_COARSE, config.N_SAMPLES_FINE,
                config.NEAR, config.FAR, config.CHUNK_SIZE, config.MAX_RAYS_PER_BATCH, occupancy_grid
            )
            frame_img = np.clip(rgb.cpu().numpy(), 0.0, 1.0)
            frames_video.append((frame_img * 255).astype(np.uint8))
            
            # Progress update per frame
            pct = 90.0 + (10.0 * (i + 1) / job_config.video_frames)
            progress.estimated_completion_pct = pct
            progress_cb(progress)

    imageio.mimsave(os.path.join(outputs_dir, "nerf_animation.gif"), frames_video, fps=12)

    print(f"[Runner] Pipeline completed. Sending COMPLETED progress.", flush=True)
    progress.active_stage = "COMPLETED"
    progress.estimated_completion_pct = 100.0
    progress_cb(progress)

    print(f"[Runner] Cleaning up CUDA context.", flush=True)
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()
