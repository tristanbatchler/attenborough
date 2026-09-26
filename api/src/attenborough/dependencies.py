from ipaddress import AddressValueError, IPv4Address, IPv6Address
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from fastapi.requests import Request
from psycopg import AsyncConnection
from pydantic import BaseModel, Field
from pydantic.networks import IPvAnyAddress
from starlette.status import HTTP_400_BAD_REQUEST

from attenborough import settings
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


class Paging(BaseModel):
    """The `page` and `take` query parameters shared by the exhibit's listing endpoints."""

    page: int = Field(default=1, ge=1, le=settings.APP_MAX_PAGE)
    take: int = Field(
        default=settings.APP_DEFAULT_PAGE_TAKE, ge=1, le=settings.APP_MAX_PAGE_TAKE
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.take


PagingQuery = Annotated[Paging, Query()]
