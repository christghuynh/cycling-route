"""Per-client rate limiting for endpoints that spend upstream API quota.

The OpenRouteService key lives on the server, so every public request spends a shared, finite
budget: one target-distance search costs up to 8 routing calls out of roughly 2,000 a day.
Counters live in the database because serverless instances share no memory.

Fixed windows are used rather than a sliding log: one small row per client per window, and a
burst at a window boundary is not worth the extra bookkeeping for abuse protection.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, insert, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import TooManyRequestsError
from app.db.models import RateLimitWindow

logger = logging.getLogger(__name__)

# Rows older than this many windows are cleaned up when a new window opens.
WINDOWS_KEPT = 3


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int

    def window_start(self, now: datetime) -> datetime:
        seconds = int(now.timestamp()) // self.window_seconds * self.window_seconds
        return datetime.fromtimestamp(seconds, tz=UTC)

    def retry_after(self, now: datetime) -> int:
        elapsed = (now - self.window_start(now)).total_seconds()
        return max(1, int(self.window_seconds - elapsed))


async def enforce(
    session: AsyncSession, client: str, policy: RateLimitPolicy, now: datetime | None = None
) -> None:
    """Count this request and raise `TooManyRequestsError` once the policy's limit is passed.

    A failure to record the request is logged and allowed through: the limiter protects a quota,
    so it should never be the reason a working request fails.
    """
    now = now or datetime.now(UTC)
    window_start = policy.window_start(now)
    key = f"{policy.name}:{client}"

    try:
        count = await _increment(session, key, window_start)
    except SQLAlchemyError:
        logger.exception("Rate limit bookkeeping failed for %s; allowing the request", key)
        await session.rollback()
        return

    if count > policy.limit:
        raise TooManyRequestsError(
            "Too many requests. This demo shares one routing API key, so it limits how often "
            "routes can be generated. Please try again shortly.",
            policy.retry_after(now),
        )


async def _increment(session: AsyncSession, key: str, window_start: datetime) -> int:
    """Add one to the window's counter, creating it if needed, and return the new count."""
    statement = (
        update(RateLimitWindow)
        .where(RateLimitWindow.key == key, RateLimitWindow.window_start == window_start)
        .values(count=RateLimitWindow.count + 1)
        .returning(RateLimitWindow.count)
    )
    count = (await session.execute(statement)).scalar_one_or_none()

    if count is None:
        try:
            await session.execute(
                insert(RateLimitWindow).values(key=key, window_start=window_start, count=1)
            )
            count = 1
        except IntegrityError:
            # Another instance opened the same window first; count against theirs.
            await session.rollback()
            count = (await session.execute(statement)).scalar_one()

    await session.commit()
    return int(count)


async def clean_up_old_windows(session: AsyncSession, policy: RateLimitPolicy) -> None:
    """Delete counters that can no longer be reached, so the table stays small.

    Housekeeping is best-effort: a failure here must not fail the request being served.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=policy.window_seconds * WINDOWS_KEPT)
    try:
        await session.execute(delete(RateLimitWindow).where(RateLimitWindow.window_start < cutoff))
        await session.commit()
    except SQLAlchemyError:
        logger.warning("Could not clean up old rate limit windows", exc_info=True)
        await session.rollback()
