# ─────────────────────────────────────────────────────────────────────────────
# Neo3D — Backend Dockerfile
# Service: FastAPI API server
# Why python:3.11-slim?
#   - Slim base = ~150MB vs 1GB for full Python image
#   - No COLMAP here — COLMAP runs in the worker container only
#   - opencv-python-headless instead of opencv-python (no GUI deps needed)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Install only what's absolutely needed at OS level
# libgomp1 = OpenMP runtime (used by opencv/numpy for parallel ops)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
# Running as root inside containers is a security anti-pattern
RUN useradd -m -u 1001 -s /bin/bash neo3d

WORKDIR /app

# ─── Install Python dependencies ──────────────────────────────────────────────
# Copy requirements first — Docker layer caching means this only re-runs when
# requirements.txt changes, not on every code change
COPY backend/requirements.txt ./requirements.txt

# Use headless OpenCV (no X11/GUI deps) — critical for server environments
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Copy application code ───────────────────────────────────────────────────
COPY backend/ .

# Create required directories (volumes will overlay these at runtime)
RUN mkdir -p datasets outputs logs && \
    chown -R neo3d:neo3d /app

# Switch to non-root user
USER neo3d

# ─── Health check ─────────────────────────────────────────────────────────────
# Docker (and docker-compose) will poll this to determine container health
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health/ || exit 1

# ─── Expose & Run ─────────────────────────────────────────────────────────────
EXPOSE 8001

# Use environment variable for workers (default 1 for single-GPU machine)
# --no-access-log reduces noise; structured logging handles request logging
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8001 --workers 1"]
