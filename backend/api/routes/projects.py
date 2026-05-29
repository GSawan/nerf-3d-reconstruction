"""
Projects API routes.
Endpoints:
  POST   /projects/           — create project
  GET    /projects/           — list current user's projects
  GET    /projects/{id}       — get single project + its sessions
  PATCH  /projects/{id}       — update project name/description
  DELETE /projects/{id}       — delete project (cascades to sessions+models)
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from db.models import Project, ReconstructionSession, User
from api.core.deps import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class SessionSummary(BaseModel):
    id: str
    status: str
    image_count: int
    camera_count: int
    point_count: int
    created_at: datetime
    completed_at: Optional[datetime]


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_public: bool
    thumbnail_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    session_count: int = 0


class ProjectDetailResponse(ProjectResponse):
    sessions: List[SessionSummary] = []


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(
        id=str(uuid.uuid4()),
        owner_id=user.id,
        name=body.name,
        description=body.description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id, name=project.name, description=project.description,
        is_public=project.is_public, thumbnail_url=project.thumbnail_url,
        created_at=project.created_at, updated_at=project.updated_at,
    )


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    return [
        ProjectResponse(
            id=p.id, name=p.name, description=p.description,
            is_public=p.is_public, thumbnail_url=p.thumbnail_url,
            created_at=p.created_at, updated_at=p.updated_at,
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id and not project.is_public:
        raise HTTPException(status_code=403, detail="Access denied")

    sess_result = await db.execute(
        select(ReconstructionSession)
        .where(ReconstructionSession.project_id == project_id)
        .order_by(ReconstructionSession.created_at.desc())
    )
    sessions = sess_result.scalars().all()

    return ProjectDetailResponse(
        id=project.id, name=project.name, description=project.description,
        is_public=project.is_public, thumbnail_url=project.thumbnail_url,
        created_at=project.created_at, updated_at=project.updated_at,
        session_count=len(sessions),
        sessions=[
            SessionSummary(
                id=s.id, status=s.status.value, image_count=s.image_count,
                camera_count=s.camera_count, point_count=s.point_count,
                created_at=s.created_at, completed_at=s.completed_at,
            ) for s in sessions
        ],
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.is_public is not None:
        project.is_public = body.is_public
    project.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id, name=project.name, description=project.description,
        is_public=project.is_public, thumbnail_url=project.thumbnail_url,
        created_at=project.created_at, updated_at=project.updated_at,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(project)
    await db.commit()
