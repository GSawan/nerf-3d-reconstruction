import torch
import torch.nn.functional as F

from utils.rays import get_rays


def volume_render(rgb: torch.Tensor, sigma: torch.Tensor, z_vals: torch.Tensor, white_bkgd: bool = True):
    delta = z_vals[..., 1:] - z_vals[..., :-1]
    delta = torch.cat(
        [delta, torch.ones_like(delta[..., :1]) * 1e10],
        dim=-1,
    )

    alpha = 1.0 - torch.exp(-sigma * delta)

    transmittance = torch.cumprod(
        torch.cat(
            [torch.ones_like(alpha[..., :1]), 1.0 - alpha + 1e-10],
            dim=-1,
        ),
        dim=-1,
    )[..., :-1]

    weights = transmittance * alpha

    rendered_rgb = torch.sum(weights[..., None] * rgb, dim=-2)

    acc_map = torch.sum(weights, dim=-1)
    if white_bkgd:
        rendered_rgb = rendered_rgb + (1.0 - acc_map[..., None])

    depth_map = torch.sum(weights * z_vals, dim=-1)
    depth_map = depth_map / (acc_map + 1e-10)

    return rendered_rgb, depth_map, weights


def sample_pdf(bins, weights, N_samples, deterministic: bool = False):
    weights = weights + 1e-5
    pdf = weights / torch.sum(weights, dim=-1, keepdim=True)
    cdf = torch.cumsum(pdf, dim=-1)
    cdf = torch.cat([torch.zeros_like(cdf[..., :1]), cdf], dim=-1)

    if deterministic:
        u = torch.linspace(0.0, 1.0, steps=N_samples, device=bins.device)
        u = u.expand(list(cdf.shape[:-1]) + [N_samples])
    else:
        u = torch.rand(list(cdf.shape[:-1]) + [N_samples], device=bins.device)

    inds = torch.searchsorted(cdf, u, right=True)
    below = torch.clamp(inds - 1, min=0)
    above = torch.clamp(inds, max=cdf.shape[-1] - 1)
    inds_g = torch.stack([below, above], dim=-1)

    cdf_g = torch.gather(
        cdf.unsqueeze(-2).expand(*inds_g.shape[:-1], cdf.shape[-1]),
        -1,
        inds_g,
    )

    bins_g = torch.gather(
        bins.unsqueeze(-2).expand(*inds_g.shape[:-1], bins.shape[-1]),
        -1,
        torch.clamp(inds_g, max=bins.shape[-1] - 1),
    )

    denom = cdf_g[..., 1] - cdf_g[..., 0]
    denom = torch.where(denom < 1e-5, torch.ones_like(denom), denom)

    t = (u - cdf_g[..., 0]) / denom
    samples = bins_g[..., 0] + t * (bins_g[..., 1] - bins_g[..., 0])

    return samples


def _run_network(model, encoder_xyz, encoder_dir, pts, viewdirs, point_chunk_size, occupancy_grid=None):
    pts_flat = pts.reshape(-1, 3)
    dirs_flat = viewdirs.unsqueeze(1).expand(-1, pts.shape[1], 3).reshape(-1, 3)
    
    total_pts = pts_flat.shape[0]
    mask = None
    skipped_samples = 0

    if occupancy_grid is not None:
        with torch.no_grad():
            occ_vals = occupancy_grid(pts_flat, encoder_xyz.bounds_min, encoder_xyz.bounds_max)
            mask = occ_vals > occupancy_grid.threshold
            active_count = mask.sum().item()
            
            # Safeguard: If pruning removes > 95% of samples, fallback to dense evaluation to prevent collapse
            if active_count < total_pts * 0.05:
                mask = None

    if mask is None:
        pts_active = pts_flat
        dirs_active = dirs_flat
        active_count = total_pts
    else:
        active_idx = torch.where(mask)[0]
        pts_active = pts_flat[active_idx]
        dirs_active = dirs_flat[active_idx]
        skipped_samples = total_pts - active_count

    rgb_active = None
    sigma_active = None

    for start in range(0, active_count, point_chunk_size):
        end = start + point_chunk_size
        pts_chunk = pts_active[start:end]
        dirs_chunk = dirs_active[start:end]

        pts_enc = encoder_xyz.encode(pts_chunk)
        dirs_enc = encoder_dir.encode(dirs_chunk)

        rgb_chunk, sigma_chunk = model(pts_enc, dirs_enc)
        
        # Preallocate active tensors natively mapping to AMP output dtype dynamically to save memory allocations!
        if rgb_active is None:
            rgb_active = torch.empty((active_count, 3), dtype=rgb_chunk.dtype, device=pts.device)
            sigma_active = torch.empty((active_count,), dtype=sigma_chunk.dtype, device=pts.device)
            
        rgb_active[start:end] = rgb_chunk
        sigma_active[start:end] = sigma_chunk

    # Edge case: No active samples surviving mask
    if rgb_active is None:
        rgb_active = torch.empty((0, 3), dtype=torch.float32, device=pts.device)
        sigma_active = torch.empty((0,), dtype=torch.float32, device=pts.device)

    if mask is None:
        rgb = rgb_active
        sigma = sigma_active
    else:
        rgb_out = torch.zeros(total_pts, 3, dtype=rgb_active.dtype, device=pts.device)
        sigma_out = torch.zeros(total_pts, dtype=sigma_active.dtype, device=pts.device)
        rgb_out[active_idx] = rgb_active
        sigma_out[active_idx] = sigma_active
        rgb = rgb_out
        sigma = sigma_out

    return rgb, sigma, skipped_samples, total_pts


def render_rays(
    model_coarse,
    model_fine,
    encoder_xyz,
    encoder_dir,
    rays_o: torch.Tensor,
    rays_d: torch.Tensor,
    n_coarse: int,
    n_fine: int,
    near: float,
    far: float,
    point_chunk_size: int,
    perturb: bool = False,
    occupancy_grid=None,
):
    device = rays_o.device
    n_rays = rays_o.shape[0]

    z_vals = torch.linspace(near, far, n_coarse, device=device)
    z_vals = z_vals.expand(n_rays, n_coarse)

    if perturb and n_coarse > 1:
        mids = 0.5 * (z_vals[:, 1:] + z_vals[:, :-1])
        upper = torch.cat([mids, z_vals[:, -1:]], dim=-1)
        lower = torch.cat([z_vals[:, :1], mids], dim=-1)
        t_rand = torch.rand_like(z_vals)
        z_vals = lower + (upper - lower) * t_rand

    pts = rays_o[:, None, :] + rays_d[:, None, :] * z_vals[..., :, None]
    viewdirs = F.normalize(rays_d, dim=-1)

    rgb_c, sigma_c, skipped_c, total_c = _run_network(
        model_coarse,
        encoder_xyz,
        encoder_dir,
        pts,
        viewdirs,
        point_chunk_size,
        occupancy_grid,
    )

    rgb_c = rgb_c.reshape(n_rays, n_coarse, 3)
    sigma_c = sigma_c.reshape(n_rays, n_coarse)

    rgb_map_c, depth_map_c, weights_c = volume_render(rgb_c, sigma_c, z_vals, white_bkgd=True)

    if model_fine is None or n_fine <= 0:
        return rgb_map_c, depth_map_c, rgb_map_c, depth_map_c, skipped_c, total_c

    z_mids = 0.5 * (z_vals[:, 1:] + z_vals[:, :-1])
    bins = z_mids[:, 1:-1]
    weights_for_pdf = weights_c[:, 1:-1].detach()

    z_samples = sample_pdf(
        bins=bins,
        weights=weights_for_pdf,
        N_samples=n_fine,
        deterministic=not perturb,
    )

    z_vals_fine, _ = torch.sort(torch.cat([z_vals, z_samples], dim=-1), dim=-1)

    pts_fine = rays_o[:, None, :] + rays_d[:, None, :] * z_vals_fine[..., :, None]

    rgb_f, sigma_f, skipped_f, total_f = _run_network(
        model_fine,
        encoder_xyz,
        encoder_dir,
        pts_fine,
        viewdirs,
        point_chunk_size,
        occupancy_grid,
    )

    rgb_f = rgb_f.reshape(n_rays, n_coarse + n_fine, 3)
    sigma_f = sigma_f.reshape(n_rays, n_coarse + n_fine)

    rgb_map_f, depth_map_f, _ = volume_render(rgb_f, sigma_f, z_vals_fine, white_bkgd=True)

    return rgb_map_c, depth_map_c, rgb_map_f, depth_map_f, skipped_c + skipped_f, total_c + total_f


def render_image(
    model_coarse,
    model_fine,
    encoder_xyz,
    encoder_dir,
    H: int,
    W: int,
    focal: float,
    c2w: torch.Tensor,
    n_coarse: int,
    n_fine: int,
    near: float,
    far: float,
    point_chunk_size: int,
    ray_batch_size: int,
    occupancy_grid=None,
):
    rays_o, rays_d = get_rays(H, W, focal, c2w)

    rays_o = rays_o.reshape(-1, 3).contiguous()
    rays_d = rays_d.reshape(-1, 3).contiguous()

    rgb_batches = []
    depth_batches = []

    for i in range(0, rays_o.shape[0], ray_batch_size):
        ro = rays_o[i : i + ray_batch_size]
        rd = rays_d[i : i + ray_batch_size]

        _, _, rgb_f, depth_f, _, _ = render_rays(
            model_coarse=model_coarse,
            model_fine=model_fine,
            encoder_xyz=encoder_xyz,
            encoder_dir=encoder_dir,
            rays_o=ro,
            rays_d=rd,
            n_coarse=n_coarse,
            n_fine=n_fine,
            near=near,
            far=far,
            point_chunk_size=point_chunk_size,
            perturb=False,
            occupancy_grid=occupancy_grid,
        )

        rgb_batches.append(rgb_f)
        depth_batches.append(depth_f)

    rgb = torch.cat(rgb_batches, dim=0).reshape(H, W, 3)
    depth = torch.cat(depth_batches, dim=0).reshape(H, W)

    return rgb, depth