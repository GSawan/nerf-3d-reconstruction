import threading
import queue
import time
import gc
import traceback
import torch

from utils.jobs.models import JobState, JobMetadata, JobConfig, JobProgress
from utils.execution.runner import run_reconstruction

class JobManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.job_queue = queue.Queue()
        self.active_jobs = {}       # session_id -> JobMetadata
        self.cancel_events = {}     # session_id -> threading.Event
        
        # Single background thread ensures strict GPU Locking (1 job at a time)
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def submit_job(self, session_id: str, config: JobConfig = None) -> JobMetadata:
        if config is None:
            config = JobConfig()
            
        metadata = JobMetadata(session_id=session_id, config=config)
        metadata.save()
        
        self.active_jobs[session_id] = metadata
        self.cancel_events[session_id] = threading.Event()
        
        self.job_queue.put(session_id)
        self._update_queue_positions()
        
        return metadata

    def cancel_job(self, session_id: str):
        if session_id in self.cancel_events:
            self.cancel_events[session_id].set()
            
        if session_id in self.active_jobs:
            meta = self.active_jobs[session_id]
            if meta.state in [JobState.QUEUED, JobState.PREPROCESSING]:
                meta.state = JobState.CANCELLED
                meta.save()

    def get_job_status(self, session_id: str) -> JobMetadata:
        if session_id in self.active_jobs:
            return self.active_jobs[session_id]
        return JobMetadata.load(session_id)

    def _update_queue_positions(self):
        # Update queue positions for all QUEUED jobs
        queued_sessions = list(self.job_queue.queue)
        for i, sid in enumerate(queued_sessions):
            if sid in self.active_jobs:
                self.active_jobs[sid].progress.queue_position = i + 1
                self.active_jobs[sid].save()

    def _worker_loop(self):
        while True:
            session_id = self.job_queue.get()
            try:
                print(f"\n[JobManager] Popped {session_id} from queue.", flush=True)
                self._update_queue_positions()
                
                if session_id not in self.active_jobs:
                    print(f"[JobManager] {session_id} not in active_jobs, skipping.", flush=True)
                    continue
                    
                meta = self.active_jobs[session_id]
                cancel_event = self.cancel_events[session_id]
                
                if meta.state == JobState.CANCELLED or cancel_event.is_set():
                    print(f"[JobManager] {session_id} was cancelled before starting.", flush=True)
                    continue
                    
                print(f"[JobManager] Starting execution for {session_id}", flush=True)
                meta.state = JobState.TRAINING
                meta.progress.queue_position = 0
                meta.timing.started_at = time.time()
                meta.save()

                retry_count = 0
                success = False
                
                while retry_count <= meta.max_retries and not success:
                    try:
                        def progress_cb(progress: JobProgress):
                            meta.progress = progress
                            if progress.active_stage == "CANCELLED":
                                meta.state = JobState.CANCELLED
                            meta.save()

                        print(f"[JobManager] Calling run_reconstruction for {session_id}...", flush=True)
                        run_reconstruction(
                            session_id=session_id,
                            job_config=meta.config,
                            progress_cb=progress_cb,
                            cancel_event=cancel_event
                        )
                        print(f"[JobManager] Returned from run_reconstruction for {session_id}.", flush=True)
                        
                        if not cancel_event.is_set():
                            meta.state = JobState.COMPLETED
                            meta.timing.completed_at = time.time()
                            meta.timing.total_runtime = meta.timing.completed_at - meta.timing.started_at
                            meta.save()
                            print(f"[JobManager] {session_id} completed successfully.", flush=True)
                        else:
                            print(f"[JobManager] {session_id} ended early due to cancellation.", flush=True)
                            meta.state = JobState.CANCELLED
                            meta.timing.completed_at = time.time()
                            meta.save()
                        
                        success = True

                    except RuntimeError as e:
                        print(f"[JobManager] RuntimeError in {session_id}: {e}", flush=True)
                        if "CUDA out of memory" in str(e):
                            meta.error_message = f"CUDA OOM (Attempt {retry_count+1}/{meta.max_retries+1})"
                        else:
                            meta.error_message = str(e)
                            
                        retry_count += 1
                        meta.retry_count = retry_count
                        
                        if retry_count > meta.max_retries:
                            meta.state = JobState.FAILED
                            meta.timing.completed_at = time.time()
                        meta.save()
                        
                    except Exception as e:
                        print(f"[JobManager] Exception in {session_id}: {traceback.format_exc()}", flush=True)
                        meta.state = JobState.FAILED
                        meta.error_message = traceback.format_exc()
                        meta.timing.completed_at = time.time()
                        meta.save()
                        break
                        
                    finally:
                        # CRITICAL: Strict GPU cleanup after every run or failure
                        print(f"[JobManager] Running GPU cleanup for {session_id}", flush=True)
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        gc.collect()

                # Remove from active tracking to free memory, rely on disk for status
                if session_id in self.active_jobs:
                    del self.active_jobs[session_id]
                if session_id in self.cancel_events:
                    del self.cancel_events[session_id]

            except Exception as e:
                print(f"[JobManager] Outer loop exception caught: {traceback.format_exc()}", flush=True)
            finally:
                print(f"[JobManager] Releasing queue lock for {session_id} in finally block.", flush=True)
                self.job_queue.task_done()
