"""Hosted Postgres URLs need translating before asyncpg will accept them."""

import pytest

from app.db.database import normalize_database_url


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_scheme_is_rewritten_to_the_async_driver(scheme: str) -> None:
    url, _ = normalize_database_url(f"{scheme}://user:pw@host/db")
    assert url.startswith("postgresql+asyncpg://")


def test_sslmode_becomes_an_asyncpg_connect_argument() -> None:
    url, connect_args = normalize_database_url(
        "postgresql://user:pw@ep-cool.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    # asyncpg rejects libpq-only parameters in the URL.
    assert "sslmode" not in url
    assert "channel_binding" not in url
    assert connect_args == {"ssl": "require"}


def test_other_query_parameters_are_preserved() -> None:
    url, connect_args = normalize_database_url(
        "postgresql://user:pw@host/db?sslmode=require&application_name=planner"
    )
    assert "application_name=planner" in url
    assert connect_args == {"ssl": "require"}


def test_sslmode_disable_does_not_request_tls() -> None:
    _, connect_args = normalize_database_url("postgresql://user:pw@host/db?sslmode=disable")
    assert connect_args == {}


def test_local_url_is_unchanged() -> None:
    original = "postgresql+asyncpg://cycling:cycling@localhost:5432/cycling_routes"
    url, connect_args = normalize_database_url(original)
    assert url == original
    assert connect_args == {}


def test_sqlite_url_is_left_alone() -> None:
    url, connect_args = normalize_database_url("sqlite+aiosqlite:///./test.db")
    assert url == "sqlite+aiosqlite:///./test.db"
    assert connect_args == {}
