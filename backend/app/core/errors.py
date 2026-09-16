"""Domain exceptions. The API layer maps these to HTTP responses."""


class RoutePlannerError(Exception):
    """Base class for errors that should be shown to the user."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LocationNotFoundError(RoutePlannerError):
    status_code = 422
    code = "location_not_found"


class TripValidationError(RoutePlannerError):
    """The request is well-formed but the trip it describes does not make sense."""

    status_code = 422
    code = "invalid_trip"


class NoRouteFoundError(RoutePlannerError):
    status_code = 404
    code = "no_route_found"


class RouteNotFoundError(RoutePlannerError):
    status_code = 404
    code = "route_not_found"


class TooManyRequestsError(RoutePlannerError):
    """The client has made too many requests to an endpoint that costs us upstream quota."""

    status_code = 429
    code = "too_many_requests"

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ExternalServiceError(RoutePlannerError):
    """An upstream API failed, timed out, or returned something we could not parse."""

    status_code = 502
    code = "external_service_error"

    def __init__(self, service: str, message: str) -> None:
        super().__init__(message)
        self.service = service


class RateLimitedError(ExternalServiceError):
    status_code = 503
    code = "rate_limited"


class QuotaExceededError(ExternalServiceError):
    """An upstream API's quota for our key is used up until it resets (usually daily)."""

    status_code = 503
    code = "quota_exceeded"


class ConfigurationError(RoutePlannerError):
    status_code = 503
    code = "service_not_configured"


class PersistenceError(RoutePlannerError):
    status_code = 503
    code = "database_error"
