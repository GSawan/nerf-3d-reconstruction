"""
AWS S3 service.
Handles:
  - Uploading files to S3 (uploads/, outputs/)
  - Generating pre-signed download URLs
  - Checking if S3 is configured (graceful degradation to local file serving)
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "")

# S3 is only active when all config values are present
S3_ENABLED = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and S3_BUCKET)

_s3_client = None


def _get_client():
    """Lazily create the boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        if not S3_ENABLED:
            return None
        try:
            import boto3
            _s3_client = boto3.client(
                "s3",
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            )
        except ImportError:
            logger.warning("boto3 not installed — S3 upload disabled")
            return None
    return _s3_client


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_file(local_path: str, s3_key: str, content_type: str = "application/octet-stream") -> bool:
    """
    Upload a local file to S3.
    Returns True on success, False if S3 is not configured or upload fails.
    S3 key structure:
      uploads/<session_id>/<filename>
      outputs/<session_id>/model.ply
    """
    client = _get_client()
    if client is None:
        return False

    try:
        client.upload_file(
            local_path,
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info(f"S3 upload success: s3://{S3_BUCKET}/{s3_key}")
        return True
    except Exception as e:
        logger.error(f"S3 upload failed for {s3_key}: {e}")
        return False


def upload_bytes(data: bytes, s3_key: str, content_type: str = "application/octet-stream") -> bool:
    """Upload raw bytes to S3."""
    client = _get_client()
    if client is None:
        return False

    try:
        client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
        )
        return True
    except Exception as e:
        logger.error(f"S3 put_object failed for {s3_key}: {e}")
        return False


# ── Pre-signed URLs ───────────────────────────────────────────────────────────

def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> Optional[str]:
    """
    Generate a time-limited pre-signed URL for a private S3 object.
    expires_in: seconds until URL expires (default 1 hour).
    Returns None if S3 is not configured.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except Exception as e:
        logger.error(f"Failed to generate pre-signed URL for {s3_key}: {e}")
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_s3_key_for_output(session_id: str, filename: str = "model.ply") -> str:
    """Standard S3 key for a reconstruction output file."""
    return f"outputs/{session_id}/{filename}"


def get_s3_key_for_upload(session_id: str, filename: str) -> str:
    """Standard S3 key for an uploaded image."""
    return f"uploads/{session_id}/{filename}"


def is_s3_enabled() -> bool:
    return S3_ENABLED
