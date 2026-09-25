from ipaddress import AddressValueError, IPv4Address, IPv6Address
from logging import getLogger
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.requests import Request
from psycopg import AsyncConnection
from pydantic.networks import IPvAnyAddress
from starlette.status import HTTP_400_BAD_REQUEST

from attenborough import settings
from attenborough.db.ops import get_db_conn

logger = getLogger("attenborough.dependencies")


def str2ip(ip_str: str) -> IPvAnyAddress:
    try:
        return IPv4Address(ip_str)
    except AddressValueError:
        try:
            return IPv6Address(ip_str)
        except AddressValueError:
            raise AddressValueError(f"{ip_str} is not a valid IP address")


async def get_request_origin(request: Request) -> IPvAnyAddress:
    if real_ip := request.headers.get(settings.REAL_IP_HEADER):
        try:
            return str2ip(real_ip)
        except AddressValueError:
            # A trusted proxy always sets a valid address, so a malformed value was
            # sent by the peer itself: attribute the request to that peer instead.
            logger.warning(
                "Ignoring unparseable %s header; using peer address",
                settings.REAL_IP_HEADER,
            )

    if not request.client:
        raise HTTPException(HTTP_400_BAD_REQUEST, "IP address undetectable")

    return str2ip(request.client.host)


RequestOrigin = Annotated[IPvAnyAddress, Depends(get_request_origin)]
DBConn = Annotated[AsyncConnection, Depends(get_db_conn)]
