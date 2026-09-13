import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from attenborough.db import ops, queries
from attenborough.dependencies import get_request_origin

logger = logging.getLogger("attenborough.telemetry")


def get_router_group(path: str) -> str:
    """Classify the incoming path to populate the router_group field."""
    if path.startswith("/exhibit"):
        return "exhibit"
    if path.startswith("/docs") or path.startswith("/openapi.json"):
        return "system"
    return "honeypot"


class TelemetryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 1. Resolve origin IP address safely
        try:
            origin_ip = str(await get_request_origin(request))
        except Exception:
            origin_ip = request.client.host if request.client else "0.0.0.0"

        # 2. Extract request metadata
        method = request.method
        path = request.url.path
        router_group = get_router_group(path)
        user_agent = request.headers.get("user-agent")
        
        # Format headers into JSON string for logging
        headers_dict = dict(request.headers)
        headers_json = json.dumps(headers_dict)

        # 3. Process the actual endpoint request
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            # 4. Asynchronously log telemetry to Postgres using connection pool
            # Skipping healthcheck routes if you add them later
            if path != "/healthz":
                try:
                    async with ops.db_conn_pool.connection() as conn:
                        await conn.set_autocommit(True)
                        await queries.create_telemetry_hit(
                            conn,
                            ip_address=origin_ip,
                            method=method,
                            path=path,
                            router_group=router_group,
                            user_agent=user_agent,
                            headers=headers_json,
                            status_code=status_code,
                        )
                except Exception as err:
                    logger.error("Failed to record telemetry hit: %s", err)