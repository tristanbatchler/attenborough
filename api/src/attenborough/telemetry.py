"""Writing `telemetry_hits`: every recorded request goes through `record_hit`.

It has two callers, one per way a visitor's request reaches us: `TelemetryMiddleware` for requests the
API serves itself, and `POST /ingest/hits` for requests the decoy app (decoy/) served and reported.
"""

import json
import logging
from collections.abc import Mapping

from psycopg import Error as PsycopgError

from attenborough.db import queries
from attenborough.db.ops import get_db_context
from attenborough.router.group import RouterGroup

logger = logging.getLogger(__name__)

# The request header recorded as each hit's user agent.
USER_AGENT_HEADER = "user-agent"
# How much of a request body is stored; body_size keeps the full length (see schema.sql).
MAX_STORED_BODY_BYTES = 64 * 1024


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
        async with get_db_context() as db_conn:
            await queries.create_telemetry_hit(
                db_conn,
                ip_address=ip_address,
                method=method,
                path=path,
                query=query,
                router_group=router_group.value,
                user_agent=headers.get(USER_AGENT_HEADER),
                headers=json.dumps(dict(headers)),
                body=None if body is None else memoryview(body[:MAX_STORED_BODY_BYTES]),
                body_size=None if body is None else len(body),
                status_code=status_code,
            )
    except PsycopgError:
        logger.exception("Failed to record telemetry for %s %r", method, path)
