import numpy as np

def calculate_aabb(transforms: dict) -> list:
    """
    Calculates the Axis-Aligned Bounding Box (AABB) of the camera positions.
    Placeholder abstraction for future true COLMAP normalization.
    """
    positions = []
    for frame in transforms.get("frames", []):
        matrix = np.array(frame["transform_matrix"])
        # Position is the translation component (last column)
        pos = matrix[:3, 3]
        positions.append(pos)
        
    if not positions:
        return [[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]]
        
    positions = np.array(positions)
    min_bounds = positions.min(axis=0).tolist()
    max_bounds = positions.max(axis=0).tolist()
    
    return [min_bounds, max_bounds]


def normalize_scene(transforms: dict) -> dict:
    """
    Normalizes the camera transforms so the scene is centered and scaled safely 
    for the HashEncoder bounds [-1, 1].
    Currently, our synthetic cameras are perfectly normalized, so this just 
    demonstrates the pipeline abstraction and calculates bounding boxes.
    """
    
    # In a full COLMAP pipeline, we would shift the coordinate frame here
    # to center on the point cloud centroid, and scale by a uniform factor.
    
    aabb = calculate_aabb(transforms)
    
    # We append the calculated aabb to the metadata
    transforms["aabb_scale"] = 1.0
    transforms["aabb"] = aabb
    
    return transforms
