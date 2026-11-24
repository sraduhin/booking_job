from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from alembic import command
from alembic.config import Config
import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.cache as cache
import app.db as db
from app.main import app
from app.config import get_settings

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://booking:booking@localhost:25432/booking_test"
)
DEFAULT_TEST_REDIS_URL = "redis://localhost:26379/15"


def _test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _to_psycopg_url(async_url: str) -> str:
    return async_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _admin_url(async_url: str) -> str:
    parsed = urlparse(_to_psycopg_url(async_url))
    return urlunparse(parsed._replace(path="/postgres"))


def _db_name(async_url: str) -> str:
    return urlparse(_to_psycopg_url(async_url)).path.lstrip("/")


def _ensure_database(async_url: str) -> None:
    name = _db_name(async_url)
    with psycopg.connect(_admin_url(async_url), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{name}"')


def _run_migrations(async_url: str) -> None:
    os.environ["DATABASE_URL"] = async_url
    get_settings.cache_clear()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", async_url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = _test_database_url()
    _ensure_database(url)
    _run_migrations(url)
    return url


def _test_redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL", DEFAULT_TEST_REDIS_URL)


@pytest_asyncio.fixture
async def patch_app_db(test_database_url: str) -> AsyncIterator[None]:
    os.environ["DATABASE_URL"] = test_database_url
    os.environ["REDIS_URL"] = _test_redis_url()
    # Не цеплять pydevd из .env во время pytest
    os.environ["DEBUG"] = "false"
    get_settings.cache_clear()

    engine = create_async_engine(
        test_database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
    )
    session_local = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    db.engine = engine
    db.SessionLocal = session_local

    redis_client = Redis.from_url(
        _test_redis_url(),
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    try:
        await redis_client.ping()
    except Exception as exc:  # noqa: BLE001
        await redis_client.aclose()
        pytest.skip(f"Redis unavailable for tests: {exc}")

    await redis_client.flushdb()
    cache.set_redis(redis_client)

    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE bookings, events, users RESTART IDENTITY CASCADE")
        )
        await conn.execute(text("INSERT INTO events (capacity) VALUES (10)"))
        await conn.execute(
            text("INSERT INTO users (id) SELECT n FROM generate_series(1, 100) AS n")
        )

    try:
        yield
    finally:
        await redis_client.flushdb()
        await redis_client.aclose()
        cache.set_redis(None)
        await engine.dispose()


@pytest_asyncio.fixture
async def client(patch_app_db: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_b(patch_app_db: None) -> AsyncIterator[AsyncClient]:
    """Второй клиент для гонок"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def redis_client(patch_app_db: None) -> Redis:
    client = cache.get_redis()
    assert client is not None
    return client


@pytest_asyncio.fixture
async def session(patch_app_db: None) -> AsyncIterator[AsyncSession]:
    async with db.SessionLocal() as s:
        yield s


@pytest.fixture
def event_id() -> int:
    return 1


def auth_headers(user_id: int, dedup_id: int | None = None) -> dict[str, str]:
    headers = {"X-User-Id": str(user_id)}
    if dedup_id is not None:
        headers["Dedup-Id"] = str(dedup_id)
    return headers


async def create_booking(
    client: AsyncClient,
    *,
    user_id: int,
    event_id: int,
    count: int = 1,
    dedup_id: int,
) -> Response:
    return await client.post(
        "/bookings",
        json={"event_id": event_id, "count": count},
        headers=auth_headers(user_id, dedup_id),
    )


async def set_booking_created_at(
    session: AsyncSession, booking_id: int, created_at: datetime
) -> None:
    await session.execute(
        text("UPDATE bookings SET created_at = :ts WHERE id = :id"),
        {"ts": created_at, "id": booking_id},
    )
    await session.commit()
