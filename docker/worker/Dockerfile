# ─────────────────────────────────────────────────────────────────────────────
# Neo3D — COLMAP Worker Dockerfile
# Service: Reconstruction pipeline (feature extraction, matching, sparse mapping, PLY export)
#
# Why ubuntu:22.04 (not python:slim)?
#   - COLMAP's apt package requires Ubuntu's libGL, libboost, libceres stack
#   - python:slim is Debian-based and lacks COLMAP's Ubuntu-specific dependencies
#   - ubuntu:22.04 provides `colmap` directly via apt — no compilation needed
#
# Why NOT expose any port?
#   - Worker is NOT a server. It reads from shared volumes and writes PLY output.
#   - Communication with backend is via shared filesystem volumes only.
#   - This is the correct microservice pattern: do one thing, no unnecessary network surface.
# ─────────────────────────────────────────────────────────────────────────────

FROM ubuntu:22.04 AS base

# Prevent apt from prompting for timezone/region during install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

# ─── System packages ──────────────────────────────────────────────────────────
# colmap          = the reconstruction engine
# python3-pip     = Python package manager
# libgomp1        = OpenMP (numpy/opencv parallelism)
# libgl1          = OpenGL libs required by opencv
# libglib2.0-0    = GLib (required by opencv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    colmap \
    python3 \
    python3-pip \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Make python3 available as 'python'
RUN ln -sf /usr/bin/python3 /usr/bin/python

# ─── Python dependencies ──────────────────────────────────────────────────────
# Only install what the worker actually needs (not the full backend stack)
RUN pip3 install --no-cache-dir \
    opencv-python-headless \
    numpy

# ─── Non-root user ────────────────────────────────────────────────────────────
RUN useradd -m -u 1001 -s /bin/bash neo3d

WORKDIR /app

# ─── Copy only worker-relevant code ───────────────────────────────────────────
# We do NOT copy the full backend — worker only needs:
#   - workers/reconstruction_worker.py  (pipeline logic)
#   - services/preprocess.py            (image preprocessing)
#   - logging_config.py                 (structured logging)
COPY backend/workers/ ./workers/
COPY backend/services/ ./services/
COPY backend/logging_config.py ./logging_config.py

# Worker reads/writes from shared volumes — create mount points
RUN mkdir -p /datasets /outputs /logs && \
    chown -R neo3d:neo3d /app /datasets /outputs /logs

USER neo3d

# ─── Default entrypoint ───────────────────────────────────────────────────────
# The worker is not a daemon — it runs a single reconstruction job when invoked.
# Backend spawns it via subprocess or directly imports the module.
# For standalone testing: docker run neo3d-worker python -c "from workers.reconstruction_worker import run_reconstruction; run_reconstruction('session-id')"
CMD ["python", "-c", "print('Neo3D COLMAP Worker ready. Invoke run_reconstruction(session_id) to start.')"]
