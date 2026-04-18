"""Shared pytest fixtures for all backend tests."""

import os

# Feature 016 — provide a valid Fernet key before app.config is imported, so
# Settings() validation does not blow up in CI / dev shells that have no
# ADVISOR_ENCRYPTION_KEY set. A single fixed test key is deterministic and
# lets encrypt/decrypt round-trips work across every test file.
os.environ.setdefault(
    "ADVISOR_ENCRYPTION_KEY",
    "AY-RoXHkQOuLhK0mQBzxrC-nXiuVMuAYD3Kyo4Znw7w=",
)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base

# Use SQLite in-memory for tests (async)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
