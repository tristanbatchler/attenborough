"""The public exhibit: what visitors did, read-only. Only honeypot traffic is shown, never the
exhibit's or the system's own requests."""

from collections.abc import Sequence
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, IPvAnyAddress

from attenborough import settings
from attenborough.db import queries
from attenborough.db.enums import RouterGroup
from attenborough.dependencies import DBConn
from attenborough.events import (
    EventPage,
    HitDetail,
    IpSummary,
    fetch_events,
    hit_detail,
    ip_summary,
)

router = APIRouter(prefix="/exhibit", tags=[RouterGroup.EXHIBIT])

# The largest id a BIGINT column holds; a larger one would fail in the database, not as a 404.
_MAX_ID = 2**63 - 1


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

    def page_of[Row](self, rows: Sequence[Row]) -> tuple[Sequence[Row], bool]:
        """This page's rows, and whether there is a next page. `rows` were fetched with `offset`
        and `limit`."""
        return rows[: self.take], len(rows) > self.take


PagingQuery = Annotated[Paging, Query()]


@router.get("/feed")
async def list_recent_events(db_conn: DBConn, paging: PagingQuery) -> EventPage:
    """The latest visitor events from every IP address, newest first."""
    rows, has_next = paging.page_of(
        await queries.list_recent_events(
            db_conn, offset=paging.offset, limit=paging.limit
        )
    )
    return EventPage(items=await fetch_events(db_conn, rows), has_next=has_next)


@router.get("/ip/{ip_addr}/activity")
async def get_ip_events(
    ip_addr: IPvAnyAddress, db_conn: DBConn, paging: PagingQuery
) -> EventPage:
    """Everything one IP address did, newest first."""
    rows, has_next = paging.page_of(
        await queries.list_ip_events(
            db_conn,
            ip_address=str(ip_addr),
            offset=paging.offset,
            limit=paging.limit,
        )
    )
    return EventPage(items=await fetch_events(db_conn, rows), has_next=has_next)


@router.get("/ip/{ip_addr}/summary")
async def get_ip_summary(ip_addr: IPvAnyAddress, db_conn: DBConn) -> IpSummary:
    """What one IP address did, in numbers."""
    row = await queries.get_ip_summary(
        db_conn, ip_address=str(ip_addr), router_group=RouterGroup.HONEYPOT
    )
    return ip_summary(row)


@router.get("/hits/{hit_id}")
async def get_hit(
    hit_id: Annotated[int, Path(ge=1, le=_MAX_ID)], db_conn: DBConn
) -> HitDetail:
    """One request to the honeypot in full: its headers and its whole stored body. 404 for any
    other request, such as the exhibit's own."""
    row = await queries.get_hit(db_conn, id_=hit_id, router_group=RouterGroup.HONEYPOT)
    if row is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "No such request.")
    return hit_detail(row)
