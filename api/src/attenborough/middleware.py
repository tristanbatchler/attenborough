import json
import logging
from enum import StrEnum
from ipaddress import AddressValueError

from fastapi import HTTPException
from fastapi.routing import APIRoute
from psycopg import Error as PsycopgError
from starlette.requests import Request
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attenborough.db import queries
from attenborough.db.ops import get_db_context
from attenborough.dependencies import get_request_origin
from attenborough.router.group import RouterGroup
from attenborough.util import fire_and_forget

logger = logging.getLogger("attenborough.middleware")


class _AsgiType(StrEnum):
    """ASGI scope and event `type` values this middleware acts on."""

    HTTP = "http"
    RESPONSE_START = "http.response.start"


def _router_group(scope: Scope) -> RouterGroup:
    """Classify a finished request by the route Starlette matched, if any."""
    route = scope.get("route")
    # APIRoutes set "route" and "endpoint"; plain Starlette routes (/docs) only "endpoint".
    if route is None and "endpoint" not in scope:
        # Nothing matched: an unknown path probed by a scanner.
        return RouterGroup.HONEYPOT
    if isinstance(route, APIRoute):
        group = (route.openapi_extra or {}).get(RouterGroup.header_key)
        if isinstance(group, str):
            return RouterGroup(group)
    # Framework routes such as /docs and /openapi.json, or app-level routes.
    return RouterGroup.SYSTEM


async def _record_telemetry_hit(
    request: Request, router_group: RouterGroup, status_code: int
) -> None:
    try:
        origin = await get_request_origin(request)
    except HTTPException, AddressValueError:
        logger.warning(
            "Dropping telemetry for %s %r: origin undetectable",
            request.method,
            request.url.path,
        )
        return

    try:
        async with get_db_context() as db_conn:
            await queries.create_telemetry_hit(
                db_conn,
                ip_address=str(origin),
                method=request.method,
                path=request.url.path,
                router_group=router_group.value,
                user_agent=request.headers.get("user-agent"),
                headers=json.dumps(dict(request.headers)),
                status_code=status_code,
            )
    except PsycopgError:
        logger.exception(
            "Failed to record telemetry for %s %r", request.method, request.url.path
        )


class TelemetryMiddleware:
    """Records exactly one telemetry hit per HTTP request, whatever the outcome.

    Sits inside Starlette's ServerErrorMiddleware and outside its ExceptionMiddleware,
    so handled errors (404, 405, 422, raised HTTPExceptions) arrive here as ordinary
    responses, and unhandled exceptions pass through here before becoming a 500.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app: ASGIApp = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _AsgiType.HTTP:
            await self.app(scope, receive, send)
            return

        # Stays 500 if the app raises before starting a response.
        status_code = HTTP_500_INTERNAL_SERVER_ERROR

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            match message:
                case {"type": _AsgiType.RESPONSE_START, "status": int(status)}:
                    status_code = status
                case _:
                    pass
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Written off the request path so the DB never delays the response.
            fire_and_forget(
                _record_telemetry_hit,
                Request(scope),
                _router_group(scope),
                status_code,
            )
