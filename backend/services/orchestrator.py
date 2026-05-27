from utils.jobs.manager import JobManager

# Global singleton instance loaded at startup
job_manager = JobManager()

def get_job_manager() -> JobManager:
    return job_manager
