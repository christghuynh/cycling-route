import os
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.models import Base

# Hosted Postgres URLs (Neon, Supabase, Heroku) carry libpq options that asyncpg does not
# accept as query parameters. They are translated into connect arguments instead.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "options"}
_SSL_REQUIRED_MODES = {"require", "verify-ca", "verify-full"}


def normalize_database_url(database_url: str) -> tuple[str, dict[str, Any]]:
    """Split a Postgres URL into an asyncpg-safe URL plus connect arguments.

    `postgres://` and `postgresql://` are rewritten to the asyncpg driver, and `sslmode` is
    converted into asyncpg's `ssl` argument so hosted databases connect over TLS.
    """
    parts = urlsplit(database_url)
    scheme = parts.scheme
    if not scheme.startswith(("postgres", "postgresql")):
        # SQLite and other drivers need no translation, and their URLs do not survive a rebuild.
        return database_url, {}
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    kept_params = []
    connect_args: dict[str, Any] = {}
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key not in _LIBPQ_ONLY_PARAMS:
            kept_params.append((key, value))
        elif key == "sslmode" and value in _SSL_REQUIRED_MODES:
            connect_args["ssl"] = "require"

    url = urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept_params), parts.fragment))
    return url, connect_args


def is_serverless() -> bool:
    """True when running as a serverless function, where connections must not be pooled."""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def create_engine(database_url: str) -> AsyncEngine:
    url, connect_args = normalize_database_url(database_url)
    if is_serverless():
        # Each invocation gets a fresh connection: pooled ones do not survive between them,
        # and the database's own pooler handles reuse.
        return create_async_engine(url, connect_args=connect_args, poolclass=NullPool)
    return create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    """Create tables if they do not exist.

    Sufficient for this project's single, stable schema; a project with evolving schemas
    should switch to Alembic migrations.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session
