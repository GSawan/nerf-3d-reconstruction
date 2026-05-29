"""
SQLAlchemy async engine + session factory.
All database connections flow through get_db() dependency injection.
"""
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Read from environment — falls back to a local SQLite for dev
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./neo3d.db"
)

# aiosqlite needs check_same_thread=False, asyncpg doesn't — handled via connect_args
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all models."""
    pass


async def get_db():
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Create all tables on startup (dev/single-server use)."""
    async with engine.begin() as conn:
        from db import models  # noqa: F401 — import registers all models
        await conn.run_sync(Base.metadata.create_all)
