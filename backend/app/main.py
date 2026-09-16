import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, locations, routes
from app.api.errors import register_error_handlers
from app.core.config import Settings, get_settings
from app.db.database import create_engine, create_session_factory, create_tables


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        if settings.create_tables_on_startup:
            await create_tables(engine)
        app.state.session_factory = create_session_factory(engine)
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            app.state.http_client = client
            yield
        await engine.dispose()

    app = FastAPI(
        title="Ironman Cycle Router API",
        version="0.1.0",
        description=(
            "Generates, scores, and ranks cycling routes: loops and target-distance rides for "
            "training, or A-to-B trips."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(routes.router)
    app.include_router(locations.router)
    return app


app = create_app()
