"""Request telemetry: every recorded request goes through `record_hit`.

It has two callers, one per way a visitor's request reaches us: `TelemetryMiddleware` for requests the
API serves itself, and `POST /ingest/hits` for requests the decoy app (decoy/) served and reported.
"""

import json
import logging
from collections.abc import Mapping
from enum import StrEnum

from fastapi.routing import APIRoute
from psycopg import Error as PsycopgError
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attenborough.db import queries
from attenborough.db.enums import RouterGroup
from attenborough.db.ops import db_conn_pool
from attenborough.dependencies import get_request_origin

logger = logging.getLogger(__name__)

# The request header recorded as each hit's user agent.
USER_AGENT_HEADER = "user-agent"
# How much of a request body is stored; body_size keeps the full length (see schema.sql).
MAX_STORED_BODY_BYTES = 64 * 1024
# How the request line's bytes become text: one character per byte, so nothing is lost or decoded.
# Node reads a request line the same way, so the decoy app's reports match.
_REQUEST_LINE_ENCODING = "latin-1"


async def record_hit(
    *,
    ip_address: str,
    method: str,
    path: str,
    query: str | None,
    router_group: RouterGroup,
    headers: Mapping[str, str],
    body: bytes | None,
    status_code: int,
) -> None:
    """Record one request, with `path` and `query` exactly as sent and the whole `body` (None if it
    wasn't captured); only its first MAX_STORED_BODY_BYTES are stored. A database failure is logged,
    never raised: the visitor's response has already been decided, and recording must not change it.
    """
    try:
        async with db_conn_pool.connection() as db_conn:
            await queries.create_telemetry_hit(
                db_conn,
                ip_address=ip_address,
                method=method,
                path=path,
                query=query,
                router_group=router_group,
                user_agent=headers.get(USER_AGENT_HEADER),
                headers=json.dumps(dict(headers)),
                body=None if body is None else memoryview(body[:MAX_STORED_BODY_BYTES]),
                body_size=None if body is None else len(body),
                status_code=status_code,
            )
    except PsycopgError:
        logger.exception("Failed to record telemetry for %r %r", method, path)


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
        for tag in route.tags:
            if isinstance(tag, RouterGroup):
                return tag
    # Framework routes such as /docs and /openapi.json, or app-level routes.
    return RouterGroup.SYSTEM


async def _record_served_hit(
    request: Request, router_group: RouterGroup, status_code: int
) -> None:
    origin = get_request_origin(request)
    if origin is None:
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
            # The decoy app's reports are records of other requests, not visits.
            if router_group is not RouterGroup.INGEST:
                # A Starlette background task (what FastAPI's BackgroundTasks are built on), run
                # the way Starlette's Response.__call__ runs response.background: after the
                # response has been sent, within the request. The client never waits for it, and
                # uvicorn's graceful shutdown does. Only an unhandled exception's 500 is sent after
                # it (by ServerErrorMiddleware, which sits outside this middleware).
                telemetry = BackgroundTask(
                    _record_served_hit, Request(scope), router_group, status_code
                )
                await telemetry()
