import torch
import torch.nn as nn
import torch.nn.functional as F

class OccupancyGrid(nn.Module):
    def __init__(self, resolution=48, threshold=0.01, decay=0.95):
        super().__init__()
        self.resolution = resolution
        self.threshold = threshold
        self.decay = decay
        
        # Grid stores max density. Initialize to 0.0 (warmup protects against premature pruning).
        self.register_buffer("grid", torch.zeros(1, 1, resolution, resolution, resolution))
        
    @torch.no_grad()
    def update(self, model, encoder_xyz, bounds_min, bounds_max, chunk_size=32768):
        # Generate 3D grid points in [0, 1] range
        x = torch.linspace(0, 1, self.resolution, device=self.grid.device)
        y = torch.linspace(0, 1, self.resolution, device=self.grid.device)
        z = torch.linspace(0, 1, self.resolution, device=self.grid.device)
        
        grid_z, grid_y, grid_x = torch.meshgrid(z, y, x, indexing="ij")
        pts_norm = torch.stack([grid_x, grid_y, grid_z], dim=-1).view(-1, 3) 
        
        # Map to world space bounded by HashEncoder dynamically learned bounds
        pts_world = pts_norm * (bounds_max - bounds_min) + bounds_min
        
        sigmas = []
        for i in range(0, pts_world.shape[0], chunk_size):
            chunk = pts_world[i:i+chunk_size]
            enc = encoder_xyz.encode(chunk)
            # Forward pass through Geometry MLP
            h = F.relu(model.fc1(enc))
            h = F.relu(model.fc2(h))
            h = F.relu(model.fc3(h))
            sigma = F.softplus(model.sigma_head(h)).squeeze(-1)
            sigmas.append(sigma)
            
        sigmas = torch.cat(sigmas, dim=0).view(1, 1, self.resolution, self.resolution, self.resolution)
        
        # Soft Occupancy Confidence: Dilate the grid slightly using MaxPool3D
        # This protects thin geometry and edges from being pruned too aggressively
        sigmas_dilated = F.max_pool3d(sigmas, kernel_size=3, stride=1, padding=1)
        
        # Exponential Moving Average update
        self.grid.copy_(torch.maximum(self.grid * self.decay, sigmas_dilated))
        
    def forward(self, pts, bounds_min, bounds_max):
        # pts: (N, 3)
        # Normalize to [-1, 1] for grid_sample
        pts_norm = (pts - bounds_min) / (bounds_max - bounds_min + 1e-5)
        pts_norm = torch.clamp(pts_norm, 0.0, 1.0)
        pts_norm = pts_norm * 2.0 - 1.0 
        
        pts_grid = pts_norm.view(1, 1, 1, -1, 3)
        
        occ = F.grid_sample(self.grid, pts_grid, align_corners=True, padding_mode="border")
        occ = occ.view(-1)
        
        return occ
