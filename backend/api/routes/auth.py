"""
Auth API routes.
Endpoints:
  POST /auth/register    — email/password sign-up
  POST /auth/login       — email/password sign-in → access + refresh tokens
  POST /auth/refresh     — exchange refresh token → new access token
  POST /auth/logout      — invalidate refresh token
  GET  /auth/me          — return current user profile
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from db.models import User, OAuthProvider, AuditLog
from services.auth import (
    hash_password, authenticate_user, create_access_token,
    create_refresh_token, decode_token, get_user_by_email, get_user_by_id
)
from api.core.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: Optional[str]


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    oauth_provider: str
    is_verified: bool
    created_at: datetime


# ── Helper ────────────────────────────────────────────────────────────────────

async def _log_audit(db: AsyncSession, action: str, user_id: str = None,
                     resource_id: str = None, resource_type: str = None,
                     request: Request = None, details: str = None):
    ip = request.client.host if request else None
    ua = request.headers.get("user-agent") if request else None
    log = AuditLog(
        user_id=user_id, action=action,
        resource_type=resource_type, resource_id=resource_id,
        ip_address=ip, user_agent=ua, details=details
    )
    db.add(log)
    await db.commit()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user with email + password."""
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        display_name=body.display_name or body.email.split("@")[0],
        password_hash=hash_password(body.password),
        oauth_provider=OAuthProvider.LOCAL,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    # Store hashed refresh token
    user.refresh_token_hash = hash_password(refresh_token)
    await db.commit()

    await _log_audit(db, "user.register", user_id=user.id,
                     resource_type="user", resource_id=user.id, request=request)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password and receive tokens."""
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    user.refresh_token_hash = hash_password(refresh_token)
    user.last_login_at = datetime.utcnow()
    await db.commit()

    await _log_audit(db, "user.login", user_id=user.id,
                     resource_type="user", resource_id=user.id, request=request)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access token."""
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    new_access = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id)
    user.refresh_token_hash = hash_password(new_refresh)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Invalidate the user's refresh token."""
    current_user.refresh_token_hash = None
    await db.commit()


@router.get("/me", response_model=UserProfile)
async def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        oauth_provider=current_user.oauth_provider.value,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at,
    )
