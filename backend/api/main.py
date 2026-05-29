import os
import shutil
import time
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.core.middleware.cors import setup_cors, setup_rate_limiter

# Ensure directories exist BEFORE app creation (so StaticFiles mount succeeds)
os.makedirs("outputs", exist_ok=True)
os.makedirs("datasets", exist_ok=True)

app = FastAPI(
    title="NeRF 3D Reconstruction Backend",
    description="Upload images -> COLMAP sparse reconstruction -> PLY export -> Three.js viewer",
    version="2.0.0"
)

# Apply Middlewares
setup_cors(app)
setup_rate_limiter(app)

# Mount Routers
api_v1_prefix = "/api/v1"

from api.routes import health
app.include_router(health.router, prefix=api_v1_prefix)

from api.routes import upload
app.include_router(upload.router, prefix=api_v1_prefix)

from api.routes import reconstruction
app.include_router(reconstruction.router, prefix=api_v1_prefix)

# Static file serving — directories already created above
app.mount(f"{api_v1_prefix}/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount(f"{api_v1_prefix}/datasets", StaticFiles(directory="datasets"), name="datasets")


async def cleanup_old_datasets():
    """Remove dataset directories older than 24 hours to save disk space."""
    while True:
        try:
            now = time.time()
            if os.path.exists("datasets"):
                for session_dir in os.listdir("datasets"):
                    path = os.path.join("datasets", session_dir)
                    if os.path.isdir(path):
                        if now - os.path.getmtime(path) > 24 * 3600:
                            shutil.rmtree(path)
                            print(f"[CLEANUP] Removed stale dataset: {session_dir}", flush=True)
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}", flush=True)
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event():
    print("[API] NeRF Backend v2.0 started - COLMAP -> PLY -> Three.js pipeline", flush=True)
    asyncio.create_task(cleanup_old_datasets())


@app.on_event("shutdown")
async def shutdown_event():
    print("[API] Shutting down NeRF Backend...", flush=True)
