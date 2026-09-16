"""Translate exceptions into consistent JSON error responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import RoutePlannerError
from app.schemas.route import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)

# OpenAPI documentation for the error shape shared by all endpoints.
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse} for code in (404, 422, 502, 503)
}


def _error_response(
    status_code: int, code: str, message: str, details: list[dict[str, object]] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


async def handle_route_planner_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RoutePlannerError)
    log = logger.error if exc.status_code >= 500 else logger.info
    log("%s %s -> %s: %s", request.method, request.url.path, exc.code, exc.message)
    return _error_response(exc.status_code, exc.code, exc.message)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
        for error in jsonable_encoder(exc.errors())
    ]
    first = details[0]["message"] if details else "Invalid request."
    return _error_response(422, "invalid_request", str(first), details)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(500, "internal_error", "Something went wrong. Please try again.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RoutePlannerError, handle_route_planner_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
