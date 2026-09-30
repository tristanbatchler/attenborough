"""The public exhibit: what visitors did, read-only. Only honeypot traffic is shown, never the
exhibit's or the system's own requests."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, IPvAnyAddress

from attenborough import settings
from attenborough.db import queries
from attenborough.dependencies import DBConn
from attenborough.telemetry import RouterGroup

router = APIRouter(prefix="/exhibit", tags=[RouterGroup.EXHIBIT])


class Paging(BaseModel):
    """The `page` and `take` query parameters shared by the exhibit's listings."""

    page: int = Field(default=1, ge=1, le=settings.APP_MAX_PAGE)
    take: int = Field(
        default=settings.APP_DEFAULT_PAGE_TAKE, ge=1, le=settings.APP_MAX_PAGE_TAKE
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.take

    @property
    def limit(self) -> int:
        """One row more than a page: the extra row only says whether there is a next page."""
        return self.take + 1

    def page_of[Row: BaseModel](self, rows: Sequence[Row]) -> Page[Row]:
        """The page of `rows`, which were fetched with `offset` and `limit`."""
        return Page(items=rows[: self.take], has_next=len(rows) > self.take)


class Page[Row: BaseModel](BaseModel):
    """One page of a listing, newest first."""

    items: Sequence[Row]
    has_next: bool


PagingQuery = Annotated[Paging, Query()]


@router.get("/feed")
async def list_recent_activity(
    db_conn: DBConn, paging: PagingQuery
) -> Page[queries.ListRecentActivityRow]:
    """The latest visitor activity from every IP address, newest first."""
    rows = await queries.list_recent_activity(
        db_conn,
        router_group=RouterGroup.HONEYPOT,
        offset=paging.offset,
        limit=paging.limit,
    )
    return paging.page_of(rows)


@router.get("/ip/{ip_addr}/activity")
async def get_ip_activity(
    ip_addr: IPvAnyAddress, db_conn: DBConn, paging: PagingQuery
) -> Page[queries.ListIpActivityRow]:
    """Everything one IP address did, newest first."""
    rows = await queries.list_ip_activity(
        db_conn,
        ip_address=str(ip_addr),
        router_group=RouterGroup.HONEYPOT,
        offset=paging.offset,
        limit=paging.limit,
    )
    return paging.page_of(rows)
