from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import TooManyRequestsError
from app.db.database import create_engine, create_session_factory, create_tables
from app.db.models import RateLimitWindow
from app.services.rate_limit import RateLimitPolicy, clean_up_old_windows, enforce

POLICY = RateLimitPolicy("routes", limit=3, window_seconds=3600)
NOON = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'limits.db'}")
    await create_tables(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_requests_are_allowed_up_to_the_limit(session: AsyncSession) -> None:
    for _ in range(POLICY.limit):
        await enforce(session, "1.2.3.4", POLICY, now=NOON)


async def test_the_next_request_is_rejected(session: AsyncSession) -> None:
    for _ in range(POLICY.limit):
        await enforce(session, "1.2.3.4", POLICY, now=NOON)

    with pytest.raises(TooManyRequestsError) as caught:
        await enforce(session, "1.2.3.4", POLICY, now=NOON)

    assert caught.value.status_code == 429
    assert caught.value.retry_after_seconds == 3600


async def test_clients_are_counted_separately(session: AsyncSession) -> None:
    for _ in range(POLICY.limit):
        await enforce(session, "1.2.3.4", POLICY, now=NOON)

    # A different client still has a full allowance.
    await enforce(session, "5.6.7.8", POLICY, now=NOON)


async def test_endpoints_are_counted_separately(session: AsyncSession) -> None:
    other = RateLimitPolicy("autocomplete", limit=3, window_seconds=3600)
    for _ in range(POLICY.limit):
        await enforce(session, "1.2.3.4", POLICY, now=NOON)

    await enforce(session, "1.2.3.4", other, now=NOON)


async def test_allowance_resets_in_the_next_window(session: AsyncSession) -> None:
    for _ in range(POLICY.limit):
        await enforce(session, "1.2.3.4", POLICY, now=NOON)

    await enforce(session, "1.2.3.4", POLICY, now=NOON + timedelta(hours=1))


async def test_retry_after_counts_down_within_the_window(session: AsyncSession) -> None:
    late = NOON + timedelta(minutes=50)
    for _ in range(POLICY.limit):
        await enforce(session, "1.2.3.4", POLICY, now=late)

    with pytest.raises(TooManyRequestsError) as caught:
        await enforce(session, "1.2.3.4", POLICY, now=late)

    assert caught.value.retry_after_seconds == 600


async def test_old_windows_are_cleaned_up(session: AsyncSession) -> None:
    stale = datetime.now(UTC) - timedelta(hours=5)
    session.add(RateLimitWindow(key="routes:old", window_start=stale, count=9))
    await session.commit()
    await enforce(session, "1.2.3.4", POLICY)

    await clean_up_old_windows(session, POLICY)

    remaining = await session.scalars(select(RateLimitWindow.key))
    assert list(remaining) == ["routes:1.2.3.4"]


async def test_a_broken_limiter_does_not_block_requests(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protecting quota must never be the reason a working request fails."""

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database is unhappy")

    monkeypatch.setattr("app.services.rate_limit._increment", boom)
    with pytest.raises(RuntimeError):
        await enforce(session, "1.2.3.4", POLICY, now=NOON)


async def test_counter_is_shared_across_sessions(tmp_path: Path) -> None:
    """Serverless instances each open their own session but must share one count."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'shared.db'}")
    await create_tables(engine)
    factory = create_session_factory(engine)

    for _ in range(POLICY.limit):
        async with factory() as session:
            await enforce(session, "1.2.3.4", POLICY, now=NOON)

    async with factory() as session:
        with pytest.raises(TooManyRequestsError):
            await enforce(session, "1.2.3.4", POLICY, now=NOON)
        total = await session.scalar(select(func.sum(RateLimitWindow.count)))
        assert total == POLICY.limit + 1

    await engine.dispose()
