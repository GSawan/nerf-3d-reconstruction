import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

import config


class HashEncoder(nn.Module):
    def __init__(self, num_levels=config.HASH_NUM_LEVELS, level_dim=config.HASH_LEVEL_DIM, 
                 base_res=config.HASH_BASE_RES, max_res=config.HASH_MAX_RES, 
                 log2_hashmap_size=config.HASH_LOG2_SIZE):
        super().__init__()
        self.num_levels = num_levels
        self.level_dim = level_dim
        self.log2_hashmap_size = log2_hashmap_size
        self.hashmap_size = 1 << log2_hashmap_size
        self.output_dim = num_levels * level_dim
        
        self.register_buffer(
            "resolutions", 
            torch.round(torch.exp(torch.linspace(np.log(base_res), np.log(max_res), num_levels)))
        )
        
        self.embeddings = nn.Embedding(self.num_levels * self.hashmap_size, self.level_dim)
        nn.init.uniform_(self.embeddings.weight, a=-1e-4, b=1e-4)
        
        self.register_buffer("primes", torch.tensor([1, 2654435761, 805459861], dtype=torch.long))
        
        self.register_buffer("offsets", torch.tensor([
            [0,0,0], [1,0,0], [0,1,0], [1,1,0],
            [0,0,1], [1,0,1], [0,1,1], [1,1,1]
        ], dtype=torch.long))
        
        self.register_buffer("level_offsets", (torch.arange(self.num_levels) * self.hashmap_size).view(1, -1, 1))

        # Dynamic bounds for automatic normalization
        self.register_buffer("bounds_min", torch.tensor([-1.0, -1.0, -1.0]))
        self.register_buffer("bounds_max", torch.tensor([1.0, 1.0, 1.0]))

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        # Dynamic normalization
        if self.training:
            with torch.no_grad():
                batch_min = x.min(dim=0)[0]
                batch_max = x.max(dim=0)[0]
                self.bounds_min.copy_(torch.minimum(self.bounds_min, batch_min))
                self.bounds_max.copy_(torch.maximum(self.bounds_max, batch_max))
                
        # Normalize x into [0, 1] range based on running bounds
        x = (x - self.bounds_min) / (self.bounds_max - self.bounds_min + 1e-5)
        # Clamp to avoid going out of bounds after normalization
        x = torch.clamp(x, 0.0, 1.0 - 1e-5)

        N = x.shape[0]
        L = self.num_levels
        
        x_scaled = x.unsqueeze(1) * self.resolutions.view(1, -1, 1) # (N, L, 3)
        x_floor = torch.floor(x_scaled)
        x_frac = x_scaled - x_floor # (N, L, 3)
        
        x0 = x_floor.long() # (N, L, 3)
        
        # 8 corners
        corners = x0.unsqueeze(2) + self.offsets.view(1, 1, 8, 3) # (N, L, 8, 3)
        
        # Spatial Hash
        hashed = (corners[..., 0] * self.primes[0]) ^ (corners[..., 1] * self.primes[1]) ^ (corners[..., 2] * self.primes[2])
        hashed = hashed % self.hashmap_size # (N, L, 8)
        
        hashed_idx = hashed + self.level_offsets # (N, L, 8)
        
        features = self.embeddings(hashed_idx) # (N, L, 8, F)
        
        # Trilinear interpolation
        fx = x_frac[..., 0].unsqueeze(-1) # (N, L, 1)
        fy = x_frac[..., 1].unsqueeze(-1)
        fz = x_frac[..., 2].unsqueeze(-1)
        
        c000 = features[..., 0, :]
        c100 = features[..., 1, :]
        c010 = features[..., 2, :]
        c110 = features[..., 3, :]
        c001 = features[..., 4, :]
        c101 = features[..., 5, :]
        c011 = features[..., 6, :]
        c111 = features[..., 7, :]
        
        c00 = c000 * (1 - fx) + c100 * fx
        c10 = c010 * (1 - fx) + c110 * fx
        c01 = c001 * (1 - fx) + c101 * fx
        c11 = c011 * (1 - fx) + c111 * fx
        
        c0 = c00 * (1 - fy) + c10 * fy
        c1 = c01 * (1 - fy) + c11 * fy
        
        c = c0 * (1 - fz) + c1 * fz # (N, L, F)
        
        return c.view(N, L * self.level_dim)


class DirectionEncoder(nn.Module):
    def __init__(self, num_freqs: int):
        super().__init__()
        self.num_freqs = num_freqs
        self.output_dim = 3 + 6 * num_freqs

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        x = x.float()
        out = [x]
        for i in range(self.num_freqs):
            freq = 2.0 ** i
            out.append(torch.sin(freq * x))
            out.append(torch.cos(freq * x))
        return torch.cat(out, dim=-1)


class NeRF(nn.Module):
    def __init__(self):
        super().__init__()

        self.pos_dim = config.HASH_NUM_LEVELS * config.HASH_LEVEL_DIM
        self.dir_dim = 3 + 6 * config.DIR_FREQS
        hidden = config.HIDDEN_DIM

        # Geometry MLP: 3 layers as requested
        self.fc1 = nn.Linear(self.pos_dim, hidden)
        self.fc2 = nn.Linear(hidden, hidden)
        self.fc3 = nn.Linear(hidden, hidden)

        self.sigma_head = nn.Linear(hidden, 1)
        self.feature_head = nn.Linear(hidden, hidden)

        # Color MLP: 2 layers as requested
        self.view_fc1 = nn.Linear(hidden + self.dir_dim, hidden)
        self.view_fc2 = nn.Linear(hidden, hidden // 2)
        self.rgb_head = nn.Linear(hidden // 2, 3)

    def forward(self, x_enc: torch.Tensor, d_enc: torch.Tensor):
        h = F.relu(self.fc1(x_enc))
        h = F.relu(self.fc2(h))
        h = F.relu(self.fc3(h))

        sigma = F.softplus(self.sigma_head(h))
        feature = self.feature_head(h)

        h_dir = torch.cat([feature, d_enc], dim=-1)
        h_dir = F.relu(self.view_fc1(h_dir))
        h_dir = F.relu(self.view_fc2(h_dir))
        rgb = torch.sigmoid(self.rgb_head(h_dir))

        return rgb, sigma.squeeze(-1)