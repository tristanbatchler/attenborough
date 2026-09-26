import logging
from enum import StrEnum

from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attenborough.dependencies import get_request_origin
from attenborough.router.group import RouterGroup
from attenborough.telemetry import record_hit

logger = logging.getLogger(__name__)


# How the request line's bytes become text: one character per byte, so nothing is lost or decoded.
# Node reads a request line the same way, so the decoy app's reports match.
_REQUEST_LINE_ENCODING = "latin-1"


def _request_target(request: Request) -> tuple[str, str | None]:
    """The path and query exactly as the client sent them, not decoded or normalised. ASGI can't
    tell `/a?` from `/a`, so an empty query is recorded as none."""
    match request.scope:
        case {"raw_path": bytes(raw_path), "query_string": bytes(query_string)}:
            query = query_string.decode(_REQUEST_LINE_ENCODING) or None
            return raw_path.decode(_REQUEST_LINE_ENCODING), query
        case _:
            # uvicorn always sets both; raw_path is optional in ASGI, so fall back to the decoded URL.
            return request.url.path, request.url.query or None


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
    except HTTPException:
        logger.warning(
            "Dropping telemetry for %s %r: origin undetectable",
            request.method,
            request.url.path,
        )
        return

    path, query = _request_target(request)
    await record_hit(
        ip_address=str(origin),
        method=request.method,
        path=path,
        query=query,
        router_group=router_group,
        headers=request.headers,
        # The API serves its own routes without capturing bodies.
        body=None,
        status_code=status_code,
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
            router_group = _router_group(scope)
            # The decoy app's reports are records of other requests (telemetry.py), not visits.
            if router_group is not RouterGroup.INGEST:
                # A Starlette background task (what FastAPI's BackgroundTasks are built on), run
                # the way Starlette's Response.__call__ runs response.background: after the
                # response has been sent, within the request. The client never waits for it, and
                # uvicorn's graceful shutdown does. Only an unhandled exception's 500 is sent after
                # it (by ServerErrorMiddleware, which sits outside this middleware).
                telemetry = BackgroundTask(
                    _record_telemetry_hit, Request(scope), router_group, status_code
                )
                await telemetry()
