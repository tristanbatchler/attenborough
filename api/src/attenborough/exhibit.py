"""The public exhibit: what visitors did, read-only. Only honeypot traffic is shown, never the
exhibit's or the system's own requests."""

from collections.abc import Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from psycopg import AsyncConnection
from psycopg.errors import QueryCanceled
from pydantic import AfterValidator, BaseModel, Field, IPvAnyAddress

from attenborough import settings
from attenborough.db import queries
from attenborough.db.enums import RouterGroup
from attenborough.dependencies import DBConn
from attenborough.events import (
    FIRST_PAGE,
    MAX_ID,
    EventCursor,
    EventPage,
    HitDetail,
    IpSummary,
    ListedEvent,
    Takeover,
    fetch_events,
    fetch_locations,
    fetch_takeover,
    hit_detail,
    ip_summary,
)
from attenborough.patterns import Patterns, latest_patterns
from attenborough.search import FIELDS, Search, SearchField, suggestions, valid_query

router = APIRouter(prefix="/exhibit", tags=[RouterGroup.EXHIBIT])

# Longer than any token EventCursor.token() makes.
_MAX_CURSOR_LENGTH = 256
# The longest search query, and how long one may run before it is cancelled.
_MAX_QUERY_LENGTH = 1000
_SEARCH_TIMEOUT_MS = 3000
_TOO_SLOW = {
    "type": "search_timeout",
    "loc": ("query", "q"),
    "msg": "This search took too long. Narrow it, with a date range for instance.",
}


def _valid_cursor(token: str | None) -> str | None:
    """Rejects (422) a `before` that isn't a cursor from this API."""
    if token is not None:
        _ = EventCursor.from_token(token)
    return token


class Paging(BaseModel):
    """The `before` and `take` query parameters shared by the exhibit's listings."""

    # The previous page's `next_cursor`; omitted for the first, newest page.
    before: Annotated[
        str | None,
        Field(max_length=_MAX_CURSOR_LENGTH),
        AfterValidator(_valid_cursor),
    ] = None
    take: int = Field(
        default=settings.APP_DEFAULT_PAGE_TAKE, ge=1, le=settings.APP_MAX_PAGE_TAKE
    )

    @property
    def cursor(self) -> EventCursor:
        return (
            FIRST_PAGE if self.before is None else EventCursor.from_token(self.before)
        )

    @property
    def limit(self) -> int:
        """One row more than a page: the extra row only says whether there is a next page."""
        return self.take + 1

    def next_cursor(self, rows: Sequence[ListedEvent]) -> str | None:
        """Where the next page starts, or None if this is the last. `rows` were fetched with
        `cursor` and `limit`."""
        if len(rows) <= self.take:
            return None
        return EventCursor.after(rows[self.take - 1]).token()

    async def page_of(
        self, db_conn: AsyncConnection, rows: Sequence[ListedEvent]
    ) -> EventPage:
        items = await fetch_events(db_conn, rows[: self.take])
        return EventPage(
            items=items,
            next_cursor=self.next_cursor(rows),
            locations=await fetch_locations(
                db_conn, (event.ip_address for event in items)
            ),
        )


PagingQuery = Annotated[Paging, Query()]


class SearchPaging(Paging):
    """The feed's query parameters: paging, and a search (search.py) that picks the events."""

    # Blank: every event.
    q: Annotated[
        str, Field(max_length=_MAX_QUERY_LENGTH), AfterValidator(valid_query)
    ] = ""


@router.get("/feed")
async def list_recent_events(
    db_conn: DBConn, paging: Annotated[SearchPaging, Query()]
) -> EventPage:
    """The latest visitor events from every IP address, newest first: only those the search `q`
    matches (search.py), if given. A search that can't be run, or runs too long, is a 422 whose
    message says why."""
    cursor = paging.cursor
    if not paging.q.strip():
        rows = await queries.list_recent_events(
            db_conn,
            before_at=cursor.occurred_at,
            before_kind=cursor.kind,
            before_id=cursor.id,
            limit=paging.limit,
        )
        return await paging.page_of(db_conn, rows)
    try:
        async with db_conn.transaction():
            await queries.configure_search(db_conn, milliseconds=_SEARCH_TIMEOUT_MS)
            rows = await Search.parse(paging.q).run(db_conn, cursor, paging.limit)
    except QueryCanceled:
        raise RequestValidationError([_TOO_SLOW]) from None
    return await paging.page_of(db_conn, rows)


class SearchFieldHelp(BaseModel):
    """A field a search can name (search.py)."""

    name: SearchField
    description: str
    # The values the search box suggests; empty for open-ended ones.
    values: list[str]


@router.get("/search-fields")
async def list_search_fields(db_conn: DBConn) -> list[SearchFieldHelp]:
    """Every field a search can name, what it matches, and the values to suggest for it."""
    values = suggestions(await queries.list_country_codes(db_conn))
    return [
        SearchFieldHelp(name=name, description=text, values=values.get(name, []))
        for name, text in FIELDS.items()
    ]


@router.get("/ip/{ip_addr}/activity")
async def get_ip_events(
    ip_addr: IPvAnyAddress, db_conn: DBConn, paging: PagingQuery
) -> EventPage:
    """Everything one IP address did, newest first."""
    cursor = paging.cursor
    rows = await queries.list_ip_events(
        db_conn,
        ip_address=str(ip_addr),
        before_at=cursor.occurred_at,
        before_kind=cursor.kind,
        before_id=cursor.id,
        limit=paging.limit,
    )
    return await paging.page_of(db_conn, rows)


@router.get("/ip/{ip_addr}/summary")
async def get_ip_summary(ip_addr: IPvAnyAddress, db_conn: DBConn) -> IpSummary:
    """What one IP address did, in numbers, where it is, and whether it is banned."""
    address = str(ip_addr)
    locations = await fetch_locations(db_conn, [address])
    return ip_summary(
        await queries.get_ip_activity(db_conn, ip_address=address),
        locations.get(address),
        await queries.get_active_ip_ban(db_conn, ip_address=address),
    )


@router.get("/hits/{hit_id}")
async def get_hit(
    hit_id: Annotated[int, Path(ge=1, le=MAX_ID)], db_conn: DBConn
) -> HitDetail:
    """One request to the honeypot in full: its headers and its whole stored body. 404 for any
    other request, such as the exhibit's own."""
    row = await queries.get_hit(db_conn, id_=hit_id, router_group=RouterGroup.HONEYPOT)
    if row is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "No such request.")
    return hit_detail(row)


@router.get("/installs/{install_id}")
async def get_takeover(
    install_id: Annotated[int, Path(ge=1, le=MAX_ID)], db_conn: DBConn
) -> Takeover:
    """One install through the decoy's installer, and every login into the account it created,
    from whichever addresses, oldest first."""
    takeover = await fetch_takeover(db_conn, install_id)
    if takeover is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "No such install.")
    return takeover


@router.get("/patterns")
async def get_patterns(db_conn: DBConn) -> Patterns:
    """What visitors are after, who they are, when they come, and their tools and wordlists, in
    aggregate. Recomputed at most every few minutes (patterns.py)."""
    return await latest_patterns.get(db_conn, datetime.now(UTC))
