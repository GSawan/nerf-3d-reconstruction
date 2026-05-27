import os
import json
import random
import time

from contextlib import nullcontext

import cv2
import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from models.nerf import NeRF, HashEncoder, DirectionEncoder
from models.occupancy import OccupancyGrid
from utils.rays import get_rays
from utils.render import render_rays, render_image

import config


def load_image_rgb_white_bg(image_path: str, width: int, height: int) -> np.ndarray:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Missing image: {image_path}")

    image = imageio.imread(image_path)
    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    image = image.astype(np.float32) / 255.0

    if image.ndim == 2:
        image = np.stack([image, image, image], axis=-1)

    if image.shape[-1] == 4:
        rgb = image[..., :3]
        alpha = image[..., 3:4]
        image = rgb * alpha + (1.0 - alpha)
    else:
        image = image[..., :3]

    return np.clip(image, 0.0, 1.0).astype(np.float32)


def main():
    # Performance setup
    if torch.cuda.is_available():
        torch.set_float32_matmul_precision('high')
        
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = True

    device = torch.device(config.DEVICE)
    print("Using Device:", device)

    os.makedirs("outputs", exist_ok=True)
    os.makedirs("checkpoints", exist_ok=True)

    with open("data/lego/transforms_train.json", "r") as f:
        meta = json.load(f)

    encoder_xyz = HashEncoder().to(device)
    encoder_dir = DirectionEncoder(num_freqs=config.DIR_FREQS).to(device)

    model_coarse = NeRF().to(device)
    model_fine = NeRF().to(device)
    
    occupancy_grid = OccupancyGrid(
        resolution=config.OCC_GRID_RES,
        threshold=config.OCC_THRESHOLD,
        decay=config.OCC_DECAY
    ).to(device)

    encoder_xyz.train()
    encoder_dir.train()
    model_coarse.train()
    model_fine.train()

    optimizer = optim.Adam(
        list(model_coarse.parameters()) + 
        list(model_fine.parameters()) + 
        list(encoder_xyz.parameters()) + 
        list(encoder_dir.parameters()),
        lr=config.LEARNING_RATE,
    )

    criterion = nn.MSELoss()

    amp_enabled = device.type == "cuda"
    scaler = torch.amp.GradScaler('cuda', enabled=amp_enabled)

    loss_history = []
    psnr_history = []
    
    print("\n--- Starting Training Phase ---")

    train_views = min(config.TRAIN_VIEWS, len(meta["frames"]))

    start_train_time = time.time()
    
    # Dynamic scheduling setup
    current_ray_batch = float(config.RAYS_PER_BATCH)
    points_per_ray = config.N_SAMPLES_COARSE + config.N_SAMPLES_FINE
    
    for epoch in range(config.EPOCHS):
        epoch_start_time = time.time()
        
        # Accumulate loss strictly on GPU to avoid CPU synchronization delays inside loop
        total_loss_tensor = torch.zeros(1, device=device)
        
        # Acceleration tracking
        epoch_skipped = 0
        epoch_total_pts = 0
        
        if epoch >= config.OCC_WARMUP_EPOCHS and epoch % config.OCC_UPDATE_EVERY == 0:
            occupancy_grid.update(model_coarse, encoder_xyz, encoder_xyz.bounds_min, encoder_xyz.bounds_max)
        
        active_occupancy_grid = occupancy_grid if epoch >= config.OCC_WARMUP_EPOCHS else None

        frames = random.sample(meta["frames"], train_views)

        for frame in frames:
            image_path = os.path.join("data/lego", frame["file_path"] + ".png")
            image_np = load_image_rgb_white_bg(
                image_path,
                config.IMAGE_WIDTH,
                config.IMAGE_HEIGHT,
            )

            target_image = torch.from_numpy(image_np).to(device=device, dtype=torch.float32)
            H, W = target_image.shape[:2]

            c2w = torch.tensor(
                frame["transform_matrix"],
                dtype=torch.float32,
                device=device,
            )

            camera_angle_x = float(meta["camera_angle_x"])
            focal = float(0.5 * W / np.tan(0.5 * camera_angle_x))

            rays_o, rays_d = get_rays(H, W, focal, c2w)

            rays_o = rays_o.reshape(-1, 3).contiguous()
            rays_d = rays_d.reshape(-1, 3).contiguous()
            target_flat = target_image.reshape(-1, 3).contiguous()

            num_rays = rays_o.shape[0]
            
            # Use smoothly adjusted dynamic batch size
            batch_size = min(int(current_ray_batch), num_rays)

            ray_idx = torch.randperm(num_rays, device=device)[:batch_size]
            rays_o_batch = rays_o[ray_idx]
            rays_d_batch = rays_d[ray_idx]
            target_batch = target_flat[ray_idx]

            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast('cuda', enabled=amp_enabled):
                rgb_c, depth_c, rgb_f, depth_f, skipped, total_pts = render_rays(
                    model_coarse=model_coarse,
                    model_fine=model_fine,
                    encoder_xyz=encoder_xyz,
                    encoder_dir=encoder_dir,
                    rays_o=rays_o_batch,
                    rays_d=rays_d_batch,
                    n_coarse=config.N_SAMPLES_COARSE,
                    n_fine=config.N_SAMPLES_FINE,
                    near=config.NEAR,
                    far=config.FAR,
                    point_chunk_size=config.CHUNK_SIZE,
                    perturb=True,
                    occupancy_grid=active_occupancy_grid,
                )
                
                epoch_skipped += skipped
                epoch_total_pts += total_pts
                
                # Dynamic Ray Scheduler
                # If we pruned space, gracefully scale up ray batch to maximize GPU throughput
                if skipped > 0 and total_pts > 0:
                    active_ratio = (total_pts - skipped) / total_pts
                    target_rays_sparse = config.TARGET_ACTIVE_SAMPLES / (points_per_ray * max(active_ratio, 0.05))
                    
                    # 15-20% smooth increment clamps
                    max_increase = current_ray_batch * 1.15
                    max_decrease = current_ray_batch * 0.85
                    
                    base_target = config.TARGET_ACTIVE_SAMPLES / points_per_ray
                    
                    current_ray_batch = min(target_rays_sparse, max_increase, config.MAX_RAYS_PER_BATCH)
                    current_ray_batch = max(current_ray_batch, base_target, max_decrease)

                loss_c = criterion(rgb_c, target_batch)
                loss_f = criterion(rgb_f, target_batch)
                loss = loss_f + 0.1 * loss_c

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            if device.type == "cuda":
                torch.cuda.empty_cache()

            # Accumulate on GPU natively without triggering a sync
            total_loss_tensor += loss.detach()

        # ONLY execute ONE CPU/GPU sync per epoch when extracting items
        avg_loss = total_loss_tensor.item() / train_views
        safe_loss = max(avg_loss, 1e-10)
        psnr = -10.0 * np.log10(safe_loss)

        loss_history.append(avg_loss)
        psnr_history.append(psnr)

        epoch_time = time.time() - epoch_start_time
        max_vram = torch.cuda.max_memory_allocated() / (1024 * 1024) if device.type == "cuda" else 0
        
        skip_ratio = (epoch_skipped / epoch_total_pts * 100) if epoch_total_pts > 0 else 0.0
        
        status_msg = f"Epoch {epoch + 1} | Loss: {avg_loss:.6f} | PSNR: {psnr:.2f} | Time: {epoch_time:.2f}s | VRAM: {max_vram:.1f} MB | Batch Rays: {int(current_ray_batch)}"
        if epoch >= config.OCC_WARMUP_EPOCHS:
            status_msg += f" | Pruned: {skip_ratio:.1f}%"
        else:
            status_msg += f" | Pruned: [WARMUP]"
            
        print(status_msg)

        if (epoch + 1) % config.CHECKPOINT_EVERY == 0:
            torch.save(model_coarse.state_dict(), f"checkpoints/coarse_epoch_{epoch + 1}.pth")
            torch.save(model_fine.state_dict(), f"checkpoints/fine_epoch_{epoch + 1}.pth")
            torch.save(encoder_xyz.state_dict(), f"checkpoints/encoder_xyz_epoch_{epoch + 1}.pth")
            torch.save(occupancy_grid.state_dict(), f"checkpoints/occupancy_epoch_{epoch + 1}.pth")

    torch.save(model_coarse.state_dict(), "nerf_coarse.pth")
    torch.save(model_fine.state_dict(), "nerf_fine.pth")
    torch.save(model_fine.state_dict(), "nerf_model.pth")
    torch.save(encoder_xyz.state_dict(), "encoder_xyz.pth")
    torch.save(occupancy_grid.state_dict(), "occupancy.pth")

    print("\nModel Saved!")


if __name__ == "__main__":
    main()