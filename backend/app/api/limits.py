"""Rate limit dependencies for the endpoints that spend OpenRouteService quota."""

from fastapi import Depends, Request

from app.api.dependencies import SessionDep, SettingsDep, client_identifier
from app.services.rate_limit import RateLimitPolicy, clean_up_old_windows, enforce

ONE_HOUR = 3600


async def limit_route_generation(
    request: Request, session: SessionDep, settings: SettingsDep
) -> None:
    """A single search costs several routing calls, so this is the tighter limit."""
    if not settings.rate_limit_enabled:
        return
    policy = RateLimitPolicy("routes", settings.route_requests_per_hour, ONE_HOUR)
    await enforce(session, client_identifier(request), policy)
    await clean_up_old_windows(session, policy)


async def limit_autocomplete(request: Request, session: SessionDep, settings: SettingsDep) -> None:
    """Typing fires a request every few keystrokes, so this limit is much looser."""
    if not settings.rate_limit_enabled:
        return
    policy = RateLimitPolicy("autocomplete", settings.autocomplete_requests_per_hour, ONE_HOUR)
    await enforce(session, client_identifier(request), policy)


RouteGenerationLimit = Depends(limit_route_generation)
AutocompleteLimit = Depends(limit_autocomplete)
