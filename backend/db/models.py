"""
SQLAlchemy ORM Models.

Tables:
  - users              : Registered users (email/password or OAuth)
  - projects           : User-owned 3D reconstruction projects
  - reconstruction_sessions : Upload+pipeline sessions tied to a project
  - models             : Final 3D model outputs (PLY, etc.)
  - audit_logs         : Immutable append-only event trail
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

from db.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────

class OAuthProvider(str, enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"
    GITHUB = "github"


class ReconstructionStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    COLMAP_FEATURES = "colmap_features"
    COLMAP_MATCHING = "colmap_matching"
    COLMAP_SPARSE = "colmap_sparse"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelFormat(str, enum.Enum):
    PLY = "ply"
    OBJ = "obj"
    GLTF = "gltf"


# ──────────────────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────────────────

class User(Base):
    """
    Represents a registered user.
    Supports both local email/password auth and OAuth providers.
    password_hash is NULL for OAuth-only users.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(120), nullable=True)
    avatar_url = Column(Text, nullable=True)

    # Auth
    password_hash = Column(String(255), nullable=True)       # null for OAuth users
    oauth_provider = Column(SAEnum(OAuthProvider), default=OAuthProvider.LOCAL, nullable=False)
    oauth_sub = Column(String(255), nullable=True, index=True)  # provider's user ID

    # Tokens
    refresh_token_hash = Column(String(255), nullable=True)

    # Meta
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")


# ──────────────────────────────────────────────────────────────────────────────
# Projects
# ──────────────────────────────────────────────────────────────────────────────

class Project(Base):
    """
    A named container for one or more reconstruction attempts.
    A user can have many projects (e.g. 'Bust Sculpture', 'Room Scan').
    """
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=_uuid)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)  # S3 pre-signed or CDN URL

    is_public = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    # Relationships
    owner = relationship("User", back_populates="projects")
    sessions = relationship("ReconstructionSession", back_populates="project", cascade="all, delete-orphan")


# ──────────────────────────────────────────────────────────────────────────────
# Reconstruction Sessions
# ──────────────────────────────────────────────────────────────────────────────

class ReconstructionSession(Base):
    """
    One upload+pipeline execution.
    session_id matches the UUID used in the filesystem (datasets/<session_id>/).
    A project can have multiple sessions (re-runs, different angles, etc.).
    """
    __tablename__ = "reconstruction_sessions"

    id = Column(String(36), primary_key=True)  # == session_id from upload
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)

    # Pipeline state (mirrors JOB_STATES in reconstruction_worker.py)
    status = Column(SAEnum(ReconstructionStatus), default=ReconstructionStatus.PENDING, nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    # Upload metadata
    image_count = Column(Integer, default=0, nullable=False)
    accepted_count = Column(Integer, default=0, nullable=False)
    mode = Column(String(20), default="high", nullable=False)

    # COLMAP output stats
    camera_count = Column(Integer, default=0, nullable=False)
    point_count = Column(Integer, default=0, nullable=False)

    # S3 storage references
    s3_input_prefix = Column(String(500), nullable=True)   # s3://bucket/uploads/<session_id>/
    s3_output_prefix = Column(String(500), nullable=True)  # s3://bucket/outputs/<session_id>/

    # Timing
    created_at = Column(DateTime, default=_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="sessions")
    model = relationship("Model3D", back_populates="session", uselist=False, cascade="all, delete-orphan")


# ──────────────────────────────────────────────────────────────────────────────
# 3D Models (outputs)
# ──────────────────────────────────────────────────────────────────────────────

class Model3D(Base):
    """
    Represents the exported 3D model file for a completed reconstruction session.
    Stores the S3 key so we can generate pre-signed download URLs on demand.
    """
    __tablename__ = "models"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("reconstruction_sessions.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)

    format = Column(SAEnum(ModelFormat), default=ModelFormat.PLY, nullable=False)
    s3_key = Column(String(500), nullable=True)    # e.g. outputs/<session_id>/model.ply
    file_size_bytes = Column(Integer, nullable=True)
    point_count = Column(Integer, default=0, nullable=False)
    camera_count = Column(Integer, default=0, nullable=False)

    # Local fallback URL (used when S3 is not configured)
    local_url = Column(String(500), nullable=True)  # /api/v1/outputs/<session_id>/model.ply

    created_at = Column(DateTime, default=_now, nullable=False)

    # Relationships
    session = relationship("ReconstructionSession", back_populates="model")


# ──────────────────────────────────────────────────────────────────────────────
# Audit Logs
# ──────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable append-only audit trail. Never updated, only inserted.
    Tracks authentication events, uploads, reconstructions, downloads.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    action = Column(String(100), nullable=False)         # e.g. "user.login", "session.upload"
    resource_type = Column(String(50), nullable=True)    # e.g. "session", "model", "project"
    resource_id = Column(String(36), nullable=True)      # ID of the affected resource
    ip_address = Column(String(45), nullable=True)       # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)
    details = Column(Text, nullable=True)                # JSON-serialized extra context
    created_at = Column(DateTime, default=_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="audit_logs")
