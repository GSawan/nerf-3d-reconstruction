import os
import struct
import math
import random
import logging
import math
import logging

def generate_splat(colmap_txt_dir: str, output_splat_path: str):
    """
    Parses COLMAP points3D.txt and generates an optimized binary .splat file.
    Heuristically expands sparse points into larger splats for a dense aesthetic.
    """
    points3d_file = os.path.join(colmap_txt_dir, "points3D.txt")
    if not os.path.exists(points3d_file):
        logging.error(f"points3D.txt not found in {colmap_txt_dir}")
        return False
        
    points = []
    
    with open(points3d_file, "r") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split()
            if len(parts) >= 7:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                r, g, b = int(parts[4]), int(parts[5]), int(parts[6])
                points.append((x, y, z, r, g, b))
                
    if not points:
        logging.error("No points parsed from points3D.txt")
        return 0
        
    # Color grading (saturation boost & gamma)
    def grade_color(r, g, b):
        # normalize
        rf, gf, bf = r/255.0, g/255.0, b/255.0
        # gamma correct
        rf, gf, bf = math.pow(rf, 1/1.5), math.pow(gf, 1/1.5), math.pow(bf, 1/1.5)
        # saturation boost
        luma = 0.299 * rf + 0.587 * gf + 0.114 * bf
        sat = 1.3
        rf = luma + sat * (rf - luma)
        gf = luma + sat * (gf - luma)
        bf = luma + sat * (bf - luma)
        # clamp
        return (
            max(0, min(255, int(rf * 255))),
            max(0, min(255, int(gf * 255))),
            max(0, min(255, int(bf * 255)))
        )
        
    graded_points = []
    for (x, y, z, r, g, b) in points:
        graded_points.append((x, y, z, *grade_color(r, g, b)))
        
    # Calculate bounds and heuristic scale
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    min_z = min(p[2] for p in points)
    max_z = max(p[2] for p in points)
    
    extent = math.sqrt((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)
    # Average scale relative to extent and number of points
    base_scale = (extent / math.pow(len(points), 0.333)) * 1.8
    
    # Splat Density Amplification
    expanded_points = []
    for (x, y, z, r, g, b) in graded_points:
        # Original point
        expanded_points.append((x, y, z, r, g, b, base_scale, 255))
        
        # Duplicate with jitter to fill gaps
        # Spawn 2 extra splats nearby
        for _ in range(2):
            jx = x + random.uniform(-base_scale, base_scale) * 1.5
            jy = y + random.uniform(-base_scale, base_scale) * 1.5
            jz = z + random.uniform(-base_scale, base_scale) * 1.5
            # Jittered splats are slightly larger but softer
            expanded_points.append((jx, jy, jz, r, g, b, base_scale * 1.5, 120))
    
    # .splat binary format (antimatter15 standard)
    # per splat (32 bytes):
    # pos: 3x float32
    # scale: 3x float32
    # color: 4x uint8 (r, g, b, a)
    # rot: 4x uint8 (quaternion mapped 0-255)
    
    with open(output_splat_path, "wb") as f:
        for p in expanded_points:
            x, y, z, r, g, b, scale, a = p
            
            sx, sy, sz = scale, scale, scale
            
            qw, qx, qy, qz = 255, 128, 128, 128
            
            splat_data = struct.pack('<ffffffBBBBBBBB', 
                                     x, y, z, 
                                     sx, sy, sz, 
                                     r, g, b, a, 
                                     qx, qy, qz, qw)
            f.write(splat_data)
            
    logging.info(f"Successfully generated {output_splat_path} with {len(expanded_points)} splats.")
    return len(expanded_points)
