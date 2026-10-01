"""Visitor events as the exhibit shows them: one typed model per kind, tagged by `kind`.

A page of events is fetched in two steps: the `visitor_events` view gives the page's kinds and ids
in order, then one query per kind on the page fetches their details. The row-to-model functions
make no database calls.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Annotated, Literal

from psycopg import AsyncConnection
from pydantic import BaseModel, Field, TypeAdapter

from attenborough.db import enums, models, queries
from attenborough.db.enums import EventKind

# The field that tells the event models apart. Each model's `kind` has no default: with one, it would be optional in the OpenAPI schema, and the
# generated TypeScript couldn't narrow the union on it.


DISCRIMINATOR = "kind"


class Hit(BaseModel):
    """A request the honeypot received, as sent."""

    kind: Literal[EventKind.HIT]
    id: int
    occurred_at: datetime
    ip_address: str
    method: str
    path: str
    query: str | None
    status_code: int
    user_agent: str | None
    # The body's full length; null when no body was captured.
    body_size: int | None


class HitEvent(Hit):
    # The body's first KiB, decoded (see `decode_body`); null when no body was captured.
    body_preview: str | None
    # Whether the body is longer than the preview.
    body_truncated: bool


class HitDetail(Hit):
    headers: dict[str, str]
    # The whole stored body, decoded (see `decode_body`); null when no body was captured.
    body: str | None
    # Whether only the start of the body was stored (body_size says how long it was).
    body_truncated: bool


class LoginAttemptEvent(BaseModel):
    kind: Literal[EventKind.LOGIN_ATTEMPT]
    id: int
    occurred_at: datetime
    ip_address: str
    path: str
    username: str
    password: str
    # The decoy's simulated answer, not a real login.
    decoy_accepted: bool


class DecoyViewEvent(BaseModel):
    kind: Literal[EventKind.DECOY_VIEW]
    id: int
    occurred_at: datetime
    ip_address: str
    decoy_slug: str
    decoy_type: enums.DecoyType


class DecoyPasswordAttemptEvent(BaseModel):
    kind: Literal[EventKind.DECOY_PASSWORD_ATTEMPT]
    id: int
    occurred_at: datetime
    ip_address: str
    decoy_slug: str
    # Whether the decoy accepted the password: its answer, not access to anything real.
    decoy_accepted: bool


Event = Annotated[
    HitEvent | LoginAttemptEvent | DecoyViewEvent | DecoyPasswordAttemptEvent,
    Field(discriminator=DISCRIMINATOR),
]


class EventPage(BaseModel):
    """One page of events, newest first."""

    items: list[Event]
    has_next: bool


class IpSummary(BaseModel):
    """What one IP address did, in numbers. The times are null when it sent no requests."""

    requests: int
    distinct_paths: int
    login_attempts: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None


_headers = TypeAdapter(dict[str, str])


def decode_body(body: bytes) -> str:
    """A body as text: UTF-8 stays readable, and every other byte shows as `\\xNN`."""
    return body.decode("utf-8", errors="backslashreplace")


def truncated(body: memoryview | None, body_size: int | None) -> bool:
    """Whether `body` holds fewer bytes than the `body_size` the visitor sent."""
    return body is not None and body_size is not None and body_size > len(body)


def hit_event(row: queries.GetHitsByIdsRow) -> HitEvent:
    return HitEvent(
        kind=EventKind.HIT,
        id=row.id_,
        occurred_at=row.occurred_at,
        ip_address=row.ip_address,
        method=row.method,
        path=row.path,
        query=row.query,
        status_code=row.status_code,
        user_agent=row.user_agent,
        body_size=row.body_size,
        # The query gives an empty preview when no body was captured; body_size tells them apart.
        body_preview=None
        if row.body_size is None
        else decode_body(bytes(row.body_preview)),
        body_truncated=truncated(row.body_preview, row.body_size),
    )


def hit_detail(row: queries.GetHitRow) -> HitDetail:
    return HitDetail(
        kind=EventKind.HIT,
        id=row.id_,
        occurred_at=row.occurred_at,
        ip_address=row.ip_address,
        method=row.method,
        path=row.path,
        query=row.query,
        status_code=row.status_code,
        user_agent=row.user_agent,
        body_size=row.body_size,
        headers=_headers.validate_json(row.headers),
        body=None if row.body is None else decode_body(bytes(row.body)),
        body_truncated=truncated(row.body, row.body_size),
    )


def login_attempt_event(row: queries.GetLoginAttemptsByIdsRow) -> LoginAttemptEvent:
    return LoginAttemptEvent(
        kind=EventKind.LOGIN_ATTEMPT,
        id=row.id_,
        occurred_at=row.attempted_at,
        ip_address=row.ip_address,
        path=row.endpoint_path,
        username=row.username,
        password=row.password,
        decoy_accepted=row.was_fake_success,
    )


def decoy_view_event(row: queries.GetDecoyViewsByIdsRow) -> DecoyViewEvent:
    return DecoyViewEvent(
        kind=EventKind.DECOY_VIEW,
        id=row.id_,
        occurred_at=row.viewed_at,
        ip_address=row.ip_address,
        decoy_slug=row.decoy_slug,
        decoy_type=row.decoy_type,
    )


def decoy_password_attempt_event(
    row: queries.GetDecoyPasswordAttemptsByIdsRow,
) -> DecoyPasswordAttemptEvent:
    return DecoyPasswordAttemptEvent(
        kind=EventKind.DECOY_PASSWORD_ATTEMPT,
        id=row.id_,
        occurred_at=row.attempted_at,
        ip_address=row.ip_address,
        decoy_slug=row.decoy_slug,
        decoy_accepted=row.successful,
    )


def ip_summary(row: queries.GetIpSummaryRow | None) -> IpSummary:
    if row is None:
        return IpSummary(
            requests=0,
            distinct_paths=0,
            login_attempts=0,
            first_seen_at=None,
            last_seen_at=None,
        )
    return IpSummary(
        requests=row.requests,
        distinct_paths=row.distinct_paths,
        login_attempts=row.login_attempts,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
    )


def ids_of(kind: EventKind, page: Sequence[models.VisitorEvent]) -> list[int]:
    return [row.id_ for row in page if row.kind == kind]


def in_page_order(
    page: Sequence[models.VisitorEvent], events: Iterable[Event]
) -> list[Event]:
    """`events` in the page's order. An event deleted between the two steps is left out."""
    by_key = {(event.kind, event.id): event for event in events}
    return [by_key[key] for row in page if (key := (row.kind, row.id_)) in by_key]


async def fetch_events(
    conn: AsyncConnection, page: Sequence[models.VisitorEvent]
) -> list[Event]:
    """The details of a page of `visitor_events` rows, in the page's order. Only the kinds on the
    page are queried."""
    events: list[Event] = []
    if ids := ids_of(EventKind.HIT, page):
        events += map(hit_event, await queries.get_hits_by_ids(conn, ids=ids))
    if ids := ids_of(EventKind.LOGIN_ATTEMPT, page):
        events += map(
            login_attempt_event,
            await queries.get_login_attempts_by_ids(conn, ids=ids),
        )
    if ids := ids_of(EventKind.DECOY_VIEW, page):
        events += map(
            decoy_view_event, await queries.get_decoy_views_by_ids(conn, ids=ids)
        )
    if ids := ids_of(EventKind.DECOY_PASSWORD_ATTEMPT, page):
        events += map(
            decoy_password_attempt_event,
            await queries.get_decoy_password_attempts_by_ids(conn, ids=ids),
        )
    return in_page_order(page, events)
