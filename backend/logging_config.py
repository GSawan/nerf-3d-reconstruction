"""
Neo3D Structured Logging Configuration
---------------------------------------
Replaces all print() statements with structured JSON logging.
Inspired by Cloud Sentinel's centralized log aggregation approach,
adapted for Neo3D's single-server scale.

Usage in any module:
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("colmap_started", extra={"session_id": sid, "image_count": 40})
"""
import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    Machine-readable. Compatible with any future log aggregator (Loki, ELK, etc.)
    """
    SERVICE_NAME = "neo3d-backend"

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.SERVICE_NAME,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge any extra fields passed via extra={}
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                log_obj[key] = val

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


class HumanFormatter(logging.Formatter):
    """
    Human-readable format for local development console output.
    """
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        return f"{color}[{ts}] [{record.levelname}] {record.name}: {record.getMessage()}{self.RESET}"


def setup_logging():
    """
    Configure the root logger for Neo3D.
    - Console: human-readable in dev (LOG_FORMAT=human), JSON in production
    - File: always JSON, rotated daily, 7-day retention
    Call this ONCE at application startup.
    """
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    log_format = os.environ.get("LOG_FORMAT", "human").lower()  # "json" or "human"

    log_dir = os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "neo3d.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers (prevent duplicate logs on reload)
    root_logger.handlers.clear()

    # ── Console Handler ────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(HumanFormatter())
    root_logger.addHandler(console_handler)

    # ── File Handler (always JSON, rotated daily) ──────────────────────────
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    root_logger.info(
        "Neo3D logging initialized",
        extra={"log_level": log_level_str, "log_format": log_format, "log_file": log_file}
    )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Call setup_logging() first at app startup."""
    return logging.getLogger(name)
