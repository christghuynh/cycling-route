from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables (and `.env` locally)."""

    # A single `.env` at the repository root is used by docker compose and by local runs from
    # `backend/`; a `backend/.env` takes priority if present. Real environment variables win.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+asyncpg://cycling:cycling@localhost:5432/cycling_routes"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Optional regex for additional allowed origins, e.g. Vercel preview deployments:
    # https://.*\.vercel\.app
    cors_origin_regex: str = ""
    log_level: str = "INFO"

    # Long-lived servers create the schema at startup. Serverless deployments should run
    # `python -m scripts.init_db` once instead, so cold starts do no schema work.
    create_tables_on_startup: bool = True

    # OpenRouteService provides routing, elevation, geocoding, and autocomplete with one key.
    ors_api_key: str = ""
    ors_base_url: str = "https://api.openrouteservice.org"
    http_timeout_seconds: float = 20.0

    # Target-distance rides: how many directions to try, and how many routing calls may run at
    # once for a single request (the free ORS plan allows ~40 directions requests per minute).
    target_candidate_count: int = Field(default=4, ge=1, le=8)
    max_concurrent_routing_requests: int = Field(default=4, ge=1)

    # Route processing
    elevation_noise_threshold_m: float = 3.0
    default_cycling_speed_kmh: float = 18.0

    # Default preference weights (used when the client omits preferences)
    default_distance_weight: float = 0.5
    default_elevation_weight: float = 0.2
    default_safety_weight: float = 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()
