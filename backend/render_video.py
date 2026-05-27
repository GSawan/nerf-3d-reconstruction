import json
import os
import time

import imageio.v2 as imageio
import numpy as np
import torch

from models.nerf import NeRF, HashEncoder, DirectionEncoder
from models.occupancy import OccupancyGrid
from utils.render import render_image

import config


def trans_t(t: float):
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, t],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def rot_phi(phi: float):
    c = np.cos(phi)
    s = np.sin(phi)
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, c, -s, 0.0],
            [0.0, s, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def rot_theta(th: float):
    c = np.cos(th)
    s = np.sin(th)
    return np.array(
        [
            [c, 0.0, -s, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [s, 0.0, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def pose_spherical(theta: float, phi: float, radius: float, device: torch.device):
    c2w = trans_t(radius)
    c2w = rot_phi(np.deg2rad(phi)) @ c2w
    c2w = rot_theta(np.deg2rad(theta)) @ c2w
    c2w = np.array(
        [
            [-1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    ) @ c2w
    return torch.tensor(c2w, dtype=torch.float32, device=device)


def main():
    if torch.cuda.is_available():
        torch.set_float32_matmul_precision('high')
        torch.backends.cudnn.benchmark = True
        
    device = torch.device(config.DEVICE)
    os.makedirs("outputs", exist_ok=True)

    model_path = "nerf_fine.pth" if os.path.exists("nerf_fine.pth") else "nerf_model.pth"
    if not os.path.exists(model_path):
        raise FileNotFoundError("No trained model found. Run train.py first.")

    with open("data/lego/transforms_train.json", "r") as f:
        meta = json.load(f)

    encoder_xyz = HashEncoder().to(device)
    encoder_dir = DirectionEncoder(num_freqs=config.DIR_FREQS).to(device)
    occupancy_grid = OccupancyGrid(
        resolution=config.OCC_GRID_RES,
        threshold=config.OCC_THRESHOLD,
        decay=config.OCC_DECAY
    ).to(device)

    model_coarse = NeRF().to(device)
    model_fine = NeRF().to(device)

    model_coarse.load_state_dict(torch.load("nerf_coarse.pth", map_location=device))
    model_fine.load_state_dict(torch.load(model_path, map_location=device))
    if os.path.exists("encoder_xyz.pth"):
        encoder_xyz.load_state_dict(torch.load("encoder_xyz.pth", map_location=device))
    if os.path.exists("occupancy.pth"):
        occupancy_grid.load_state_dict(torch.load("occupancy.pth", map_location=device))

    model_coarse.eval()
    model_fine.eval()
    encoder_xyz.eval()
    encoder_dir.eval()
    occupancy_grid.eval()

    H = config.IMAGE_HEIGHT
    W = config.IMAGE_WIDTH
    focal = float(0.5 * W / np.tan(0.5 * float(meta["camera_angle_x"])))

    frames = []
    
    print(f"Starting rendering for {config.VIDEO_FRAMES} frames...")
    render_start_time = time.time()
    
    with torch.inference_mode(), torch.amp.autocast('cuda'):
        for i in range(config.VIDEO_FRAMES):
            theta = 360.0 * i / config.VIDEO_FRAMES

            c2w = pose_spherical(
                theta,
                config.NOVEL_VIEW_PHI,
                config.NOVEL_VIEW_RADIUS,
                device,
            )

            rendered_rgb, _ = render_image(
                model_coarse=model_coarse,
                model_fine=model_fine,
                encoder_xyz=encoder_xyz,
                encoder_dir=encoder_dir,
                H=H,
                W=W,
                focal=focal,
                c2w=c2w,
                n_coarse=config.N_SAMPLES_COARSE,
                n_fine=config.N_SAMPLES_FINE,
                near=config.NEAR,
                far=config.FAR,
                point_chunk_size=config.CHUNK_SIZE,
                ray_batch_size=config.MAX_RAYS_PER_BATCH,  # aggressively bulk during pure inference
                occupancy_grid=occupancy_grid,
            )

            frame = rendered_rgb.cpu().numpy()
            frame = np.clip(frame, 0.0, 1.0)
            frame = (frame * 255).astype(np.uint8)
            frames.append(frame)

            print(f"Rendered frame {i + 1}/{config.VIDEO_FRAMES}")

    total_time = time.time() - render_start_time
    print(f"Total video render time: {total_time:.2f}s ({total_time / config.VIDEO_FRAMES:.2f}s per frame)")

    imageio.mimsave("outputs/nerf_animation.gif", frames, fps=12)
    print("Animation saved as outputs/nerf_animation.gif")


if __name__ == "__main__":
    main()