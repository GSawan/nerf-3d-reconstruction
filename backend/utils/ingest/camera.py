import numpy as np

def trans_t(t: float):
    return np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, t],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float32)

def rot_phi(phi: float):
    c = np.cos(phi)
    s = np.sin(phi)
    return np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, c, -s, 0.0],
        [0.0, s, c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float32)

def rot_theta(th: float):
    c = np.cos(th)
    s = np.sin(th)
    return np.array([
        [c, 0.0, -s, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [s, 0.0, c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float32)

def generate_orbital_pose(theta: float, phi: float, radius: float):
    """
    Generates a camera-to-world transform matrix for a camera looking at the origin.
    """
    c2w = trans_t(radius)
    c2w = rot_phi(np.deg2rad(phi)) @ c2w
    c2w = rot_theta(np.deg2rad(theta)) @ c2w
    c2w = np.array([
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float32) @ c2w
    
    return c2w.tolist()

def generate_synthetic_transforms(num_frames: int, radius: float = 4.0, phi: float = -30.0) -> dict:
    """
    Generates a complete transforms.json dictionary using evenly spaced orbital cameras.
    This acts as a placeholder for a future full COLMAP pipeline.
    """
    frames = []
    for i in range(num_frames):
        theta = (360.0 * i) / num_frames
        matrix = generate_orbital_pose(theta, phi, radius)
        
        # File paths will be formatted externally
        frames.append({
            "file_path": f"train_{i:04d}",
            "transform_matrix": matrix
        })
        
    return {
        "camera_angle_x": 0.6911112070083618,  # Standard focal placeholder
        "frames": frames
    }
