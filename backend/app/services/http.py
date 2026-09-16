"""Shared HTTP error handling for external API clients."""

import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.errors import ExternalServiceError, RateLimitedError

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


def parse_response(response: httpx.Response, model: type[ModelT], service: str) -> ModelT:
    """Validate a JSON response body against a Pydantic model."""
    try:
        return model.model_validate_json(response.content)
    except ValidationError as exc:
        logger.error("Unexpected %s response: %s | body=%s", service, exc, response.text[:500])
        raise ExternalServiceError(
            service, f"The {service} service returned an unexpected response."
        ) from exc
