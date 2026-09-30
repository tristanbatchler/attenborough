from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.requests import Request
from psycopg import AsyncConnection
from starlette.status import HTTP_400_BAD_REQUEST

from attenborough.db.ops import get_db_conn


def get_request_origin(request: Request) -> IPv4Address | IPv6Address | None:
    """The client's address, or None if it isn't an IP address (e.g. a unix socket peer).

    The only source of the client address. ProxyHeadersMiddleware (main.py) has already replaced
    it with the X-Forwarded-For client, but only for peers in settings.FORWARDED_ALLOW_IPS; no
    request header is ever read here, so clients cannot choose their own attribution.
    """
    if request.client is None:
        return None
    try:
        return ip_address(request.client.host)
    except ValueError:
        return None


# Async only so that FastAPI calls it directly instead of in its threadpool.
async def _require_request_origin(request: Request) -> IPv4Address | IPv6Address:
    origin = get_request_origin(request)
    if origin is None:
        raise HTTPException(HTTP_400_BAD_REQUEST, "IP address undetectable")
    return origin


RequestOrigin = Annotated[IPv4Address | IPv6Address, Depends(_require_request_origin)]
DBConn = Annotated[AsyncConnection, Depends(get_db_conn)]
