import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RouteSearch(Base):
    """One route generation request: the locations, preferences, and when it was made."""

    __tablename__ = "route_searches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    mode: Mapped[str] = mapped_column(String(32))
    bike_type: Mapped[str] = mapped_column(String(32))
    target_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_query: Mapped[str] = mapped_column(String(200))
    start_name: Mapped[str] = mapped_column(Text)
    start_lat: Mapped[float] = mapped_column(Float)
    start_lon: Mapped[float] = mapped_column(Float)
    # Destination columns are empty for loops, which finish at the start.
    destination_query: Mapped[str | None] = mapped_column(String(200), nullable=True)
    destination_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_weight: Mapped[float] = mapped_column(Float)
    elevation_weight: Mapped[float] = mapped_column(Float)
    safety_weight: Mapped[float] = mapped_column(Float)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    routes: Mapped[list["RouteRecord"]] = relationship(
        back_populates="search",
        cascade="all, delete-orphan",
        order_by="RouteRecord.rank",
        lazy="selectin",
    )


class RateLimitWindow(Base):
    """Request count for one client, endpoint, and time window.

    Kept in the database rather than in memory because serverless deployments run many
    short-lived instances that share no state.
    """

    __tablename__ = "rate_limit_windows"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class RouteRecord(Base):
    """A generated, scored route belonging to a search."""

    __tablename__ = "routes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    search_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("route_searches.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    # [[lat, lon], ...]. Stored as JSON: no spatial queries are needed, so PostGIS is not used.
    geometry: Mapped[list[list[float]]] = mapped_column(JSON)
    # [[distance_km, elevation_m], ...]
    elevation_profile: Mapped[list[list[float]]] = mapped_column(JSON, default=list)
    way_type_shares: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    distance_km: Mapped[float] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_min: Mapped[float] = mapped_column(Float)
    safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_score: Mapped[float] = mapped_column(Float)
    elevation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float)
    repeated_share: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text)
    highlights: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    search: Mapped[RouteSearch] = relationship(back_populates="routes", lazy="joined")
