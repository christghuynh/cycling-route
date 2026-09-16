"""Shared HTTP error handling for external API clients."""

import logging
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.errors import ExternalServiceError, QuotaExceededError, RateLimitedError

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


async def send_request(
    client: httpx.AsyncClient, service: str, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    """Send a request, translating transport failures, rate limits, and 5xx into domain errors.

    4xx responses other than 429 are returned so the caller can interpret provider-specific
    error payloads.
    """
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        logger.warning("%s request timed out: %s", service, exc)
        raise ExternalServiceError(service, f"The {service} service timed out.") from exc
    except httpx.RequestError as exc:
        logger.warning("%s request failed: %r", service, exc)
        raise ExternalServiceError(service, f"Could not reach the {service} service.") from exc

    if _is_quota_exceeded(response):
        logger.warning("%s quota exceeded for this API key", service)
        raise QuotaExceededError(service, _quota_message(service, response))
    if response.status_code == 429:
        logger.warning("%s rate limited the request", service)
        raise RateLimitedError(
            service,
            f"The {service} service is rate limiting requests. Please try again shortly.",
        )
    if response.status_code >= 500:
        logger.error("%s returned %s: %s", service, response.status_code, response.text[:500])
        raise ExternalServiceError(service, f"The {service} service is currently unavailable.")
    return response


def _is_quota_exceeded(response: httpx.Response) -> bool:
    """The OpenRouteService gateway reports a spent daily quota as 403 "Quota exceeded".

    That is not an authentication failure, so it must not be reported as a rejected key.
    """
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    return isinstance(error, str) and "quota" in error.lower()


def _quota_message(service: str, response: httpx.Response) -> str:
    message = f"This app has used up today's {service} quota."
    reset = response.headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        hours = max(1, round((int(reset) - time.time()) / 3600))
        unit = "hour" if hours == 1 else "hours"
        return f"{message} It resets in about {hours} {unit}."
    return f"{message} It resets daily, so please try again later."


def parse_response(response: httpx.Response, model: type[ModelT], service: str) -> ModelT:
    """Validate a JSON response body against a Pydantic model."""
    try:
        return model.model_validate_json(response.content)
    except ValidationError as exc:
        logger.error("Unexpected %s response: %s | body=%s", service, exc, response.text[:500])
        raise ExternalServiceError(
            service, f"The {service} service returned an unexpected response."
        ) from exc
