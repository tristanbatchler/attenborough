from ipaddress import AddressValueError, IPv4Address, IPv6Address
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.requests import Request
from psycopg import AsyncConnection
from pydantic.networks import IPvAnyAddress
from starlette.status import HTTP_400_BAD_REQUEST

from attenborough.db.ops import get_db_conn


def str2ip(ip_str: str) -> IPvAnyAddress:
    try:
        return IPv4Address(ip_str)
    except AddressValueError:
        try:
            return IPv6Address(ip_str)
        except AddressValueError:
            raise AddressValueError(f"{ip_str} is not a valid IP address")


async def get_request_origin(request: Request) -> IPvAnyAddress:
    # The only source of the client address. ProxyHeadersMiddleware (main.py) has already replaced
    # it with the X-Forwarded-For client, but only for peers in settings.FORWARDED_ALLOW_IPS; no
    # request header is ever read here, so clients cannot choose their own attribution.
    host = request.client.host if request.client else ""
    try:
        return str2ip(host)
    except AddressValueError:
        raise HTTPException(HTTP_400_BAD_REQUEST, "IP address undetectable") from None


RequestOrigin = Annotated[IPvAnyAddress, Depends(get_request_origin)]
DBConn = Annotated[AsyncConnection, Depends(get_db_conn)]
