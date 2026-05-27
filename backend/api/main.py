import os
import shutil
import time
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.routes import health, upload, jobs, sessions, outputs, reconstruction
from api.core.middleware.cors import setup_cors, setup_rate_limiter

app = FastAPI(
    title="NeRF Engine Backend",
    description="Scalable neural rendering ingestion & processing API",
    version="0.1.0"
)

# Apply Middlewares
setup_cors(app)
setup_rate_limiter(app)

# Mount Routers
api_v1_prefix = "/api/v1"
app.include_router(health.router, prefix=api_v1_prefix)
app.include_router(upload.router, prefix=api_v1_prefix)
app.include_router(reconstruction.router, prefix=api_v1_prefix)
app.include_router(jobs.router, prefix=api_v1_prefix)
app.include_router(sessions.router, prefix=api_v1_prefix)
# outputs.router is disabled in favor of the StaticFiles mount below
# app.include_router(outputs.router, prefix=api_v1_prefix)

# Expose outputs directory for static file serving under /api/v1/outputs
app.mount(f"{api_v1_prefix}/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount(f"{api_v1_prefix}/datasets", StaticFiles(directory="datasets"), name="datasets")

async def cleanup_old_datasets():
    while True:
        try:
            now = time.time()
            if os.path.exists("datasets"):
                for session_dir in os.listdir("datasets"):
                    path = os.path.join("datasets", session_dir)
                    if os.path.isdir(path):
                        # Delete if older than 24h
                        if now - os.path.getmtime(path) > 24 * 3600:
                            shutil.rmtree(path)
                            print(f"[CLEANUP] Removed stale dataset: {session_dir}", flush=True)
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}", flush=True)
        await asyncio.sleep(3600)  # Check every hour

@app.on_event("startup")
async def startup_event():
    # Ensure output directory exists
    os.makedirs("outputs", exist_ok=True)
    print("[API] Starting NeRF Backend API...", flush=True)
    asyncio.create_task(cleanup_old_datasets())

@app.on_event("shutdown")
async def shutdown_event():
    print("[API] Shutting down NeRF Backend API...", flush=True)

