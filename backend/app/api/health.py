import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(session: SessionDep) -> JSONResponse:
    """Liveness plus a database connectivity check."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check could not reach the database")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
