"""Visitor events as the exhibit shows them: one typed model per kind, tagged by `kind`.

A page of events is fetched in two steps: ListRecentEvents or ListIpEvents (queries.sql) gives the
page's kinds and ids in order, then one query per kind on the page fetches their details. The row-to-model functions
make no database calls.
"""

import base64
import binascii
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, Self

from psycopg import AsyncConnection
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError

from attenborough import settings
from attenborough.db import models, queries
from attenborough.db.enums import EventKind, PathCategory

# The field that tells the event models apart. Each model's `kind` has no default: with one, it
# would be optional in the OpenAPI schema, and the generated TypeScript couldn't narrow the union
# on it.
DISCRIMINATOR = "kind"

# The largest id a BIGINT column holds.
MAX_ID = 2**63 - 1

# What the exhibit shows in place of the honeypot's own names and addresses.
HONEYPOT_PLACEHOLDER = "[honeypot]"


def honeypot_pattern(addresses: Iterable[str]) -> re.Pattern[str]:
    """Any of `addresses`, ignoring case, but not as part of a longer number: 203.0.113.5 is not
    found in 203.0.113.50 or 1203.0.113.5. Nothing else bounds a match, so a domain is found after
    `%2F` in an encoded URL, and inside a longer name (`www.<domain>`), which hides that name too.
    Longest first, so a name wins over a shorter one it contains."""
    longest_first = sorted(addresses, key=len, reverse=True)
    alternatives = "|".join(map(re.escape, longest_first))
    return re.compile(f"(?<![0-9])(?:{alternatives})(?![0-9])", re.IGNORECASE)


HONEYPOT = honeypot_pattern(settings.HONEYPOT_ADDRESSES)


def hide_honeypot(text: str) -> str:
    """`text` with each of the honeypot's names and addresses replaced by HONEYPOT_PLACEHOLDER.

    Visitors' requests name the server they reached (Host, Origin, Referer, absolute URLs, bodies
    such as WordPress's `redirect_to`). The exhibit hides that so readers can't tell where the
    honeypot is; the database keeps everything as sent. Best effort: a name sent in another
    encoding (base64, `%2E` for the dots) isn't recognised.
    """
    return HONEYPOT.sub(HONEYPOT_PLACEHOLDER, text)


def _hide_optional(text: str | None) -> str | None:
    return None if text is None else hide_honeypot(text)


class ListedEvent(Protocol):
    """An event's place in a listing: a row of ListRecentEvents or ListIpEvents."""

    @property
    def kind(self) -> EventKind: ...
    @property
    def id_(self) -> int: ...
    @property
    def occurred_at(self) -> datetime: ...


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
    # What the path was after: a guess from the path alone (schema.sql, path_category).
    category: PathCategory
    # Whether the decoy refused it because the address was banned.
    banned: bool
    # Whether an admin's response rule answered it instead of the decoy's own page (what the rule
    # said is private).
    custom_response: bool


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


class CanaryOrigin(BaseModel):
    """Where a canary password was handed out: the leaked file, to whom, and when."""

    path: str
    ip_address: str
    issued_at: datetime


class InstallOrigin(BaseModel):
    """The install that created the account a login used: which one, from where, and when."""

    id: int
    ip_address: str
    attempted_at: datetime


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
    # Set when the password was a canary from one of the decoy's leaked files.
    canary: CanaryOrigin | None
    # Set when the account was one a visitor "created" through the decoy's installer.
    install: InstallOrigin | None


class InstallAttemptEvent(BaseModel):
    """Someone finishing the decoy's "unfinished" WordPress install, to take the site over.
    Nothing was installed: this is the account they chose."""

    kind: Literal[EventKind.INSTALL_ATTEMPT]
    id: int
    occurred_at: datetime
    ip_address: str
    path: str
    site_title: str
    username: str
    email: str
    # The account's password: the one chosen, or the one the decoy made up (password_generated).
    password: str
    password_generated: bool


Event = Annotated[
    HitEvent | LoginAttemptEvent | InstallAttemptEvent,
    Field(discriminator=DISCRIMINATOR),
]


_PAD = "="
_BASE64_BLOCK = 4


class EventCursor(BaseModel):
    """Where a page of events starts: just after this event, in the listings' newest-first order
    (occurred_at, kind, id). Sent to clients as an opaque token."""

    occurred_at: AwareDatetime
    kind: EventKind
    id: int = Field(ge=0, le=MAX_ID)

    @classmethod
    def after(cls, event: ListedEvent) -> Self:
        return cls(occurred_at=event.occurred_at, kind=event.kind, id=event.id_)

    def token(self) -> str:
        """URL-safe base64 without its `=` padding, which URLs would escape."""
        return (
            base64.urlsafe_b64encode(self.model_dump_json().encode())
            .decode()
            .rstrip(_PAD)
        )

    @classmethod
    def from_token(cls, token: str) -> Self:
        """Raises ValueError if `token` isn't one that `token()` made."""
        try:
            padded = token + _PAD * (-len(token) % _BASE64_BLOCK)
            return cls.model_validate_json(base64.urlsafe_b64decode(padded))
        except (binascii.Error, ValidationError) as exc:
            raise ValueError("not a page cursor from this API") from exc


# Before every event, for the first page: newer than any timestamp the database holds.
FIRST_PAGE = EventCursor(
    occurred_at=datetime.max.replace(tzinfo=UTC), kind=EventKind.HIT, id=0
)


class IpLocation(BaseModel):
    """Where an address is, as a geolocation database estimated it when the address was first
    seen: never proof of where a sender is. A field is null when the database didn't know it."""

    # ISO 3166-1 alpha-2.
    country_code: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    # The autonomous system (network) announcing the address, and who runs it.
    asn: int | None
    as_organisation: str | None
    # The databases it came from, with the dates they were built.
    source: str
    located_at: datetime


class EventPage(BaseModel):
    """One page of events, newest first."""

    items: list[Event]
    # Pass it back as `before` for the next, older page; null on the last page.
    next_cursor: str | None
    # Where the page's addresses are, by address. An address that was never located is missing.
    locations: dict[str, IpLocation]


class Takeover(BaseModel):
    """An install through the decoy's installer and every login into the account it created, from
    whichever addresses: one takeover attempt, start to finish."""

    install: InstallAttemptEvent
    # Oldest first; only the first TAKEOVER_MAX_LOGINS of them.
    logins: list[LoginAttemptEvent]
    # How many logins there were in all.
    login_count: int
    # Where the addresses involved are, by address. An address that was never located is missing.
    locations: dict[str, IpLocation]


class Ban(BaseModel):
    """An address's active ban, as the public sees it: when, never why or by whom."""

    since: datetime
    # Null when it doesn't expire.
    until: datetime | None


class IpSummary(BaseModel):
    """What one IP address did, in numbers. The times are null when it sent no requests."""

    requests: int
    distinct_paths: int
    login_attempts: int
    install_attempts: int
    # Requests refused because the address was banned, at any time.
    banned_requests: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    # Null when the address was never located.
    location: IpLocation | None
    # Null when it isn't banned now.
    ban: Ban | None


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
        method=hide_honeypot(row.method),
        path=hide_honeypot(row.path),
        query=_hide_optional(row.query),
        status_code=row.status_code,
        user_agent=_hide_optional(row.user_agent),
        body_size=row.body_size,
        category=row.category,
        banned=row.banned,
        custom_response=row.custom_response is True,
        # The query gives an empty preview when no body was captured; body_size tells them apart.
        body_preview=None
        if row.body_size is None
        else hide_honeypot(decode_body(bytes(row.body_preview))),
        body_truncated=truncated(row.body_preview, row.body_size),
    )


def hit_detail(row: queries.GetHitRow) -> HitDetail:
    return HitDetail(
        kind=EventKind.HIT,
        id=row.id_,
        occurred_at=row.occurred_at,
        ip_address=row.ip_address,
        method=hide_honeypot(row.method),
        path=hide_honeypot(row.path),
        query=_hide_optional(row.query),
        status_code=row.status_code,
        user_agent=_hide_optional(row.user_agent),
        body_size=row.body_size,
        category=row.category,
        banned=row.banned,
        custom_response=row.custom_response is True,
        headers={
            hide_honeypot(name): hide_honeypot(value)
            for name, value in _headers.validate_json(row.headers).items()
        },
        body=None if row.body is None else hide_honeypot(decode_body(bytes(row.body))),
        body_truncated=truncated(row.body, row.body_size),
    )


def login_attempt_event(row: queries.GetLoginAttemptsByIdsRow) -> LoginAttemptEvent:
    return LoginAttemptEvent(
        kind=EventKind.LOGIN_ATTEMPT,
        id=row.id_,
        occurred_at=row.attempted_at,
        ip_address=row.ip_address,
        path=hide_honeypot(row.endpoint_path),
        username=hide_honeypot(row.username),
        password=hide_honeypot(row.password),
        decoy_accepted=row.was_fake_success,
        canary=None
        if row.canary_path is None
        or row.canary_ip_address is None
        or row.canary_issued_at is None
        else CanaryOrigin(
            path=hide_honeypot(row.canary_path),
            ip_address=row.canary_ip_address,
            issued_at=row.canary_issued_at,
        ),
        install=None
        if row.install_id is None
        or row.install_ip_address is None
        or row.install_attempted_at is None
        else InstallOrigin(
            id=row.install_id,
            ip_address=row.install_ip_address,
            attempted_at=row.install_attempted_at,
        ),
    )


def install_attempt_event(
    row: queries.GetInstallAttemptsByIdsRow,
) -> InstallAttemptEvent:
    return InstallAttemptEvent(
        kind=EventKind.INSTALL_ATTEMPT,
        id=row.id_,
        occurred_at=row.attempted_at,
        ip_address=row.ip_address,
        path=hide_honeypot(row.path),
        site_title=hide_honeypot(row.site_title),
        username=hide_honeypot(row.username),
        email=hide_honeypot(row.email),
        password=hide_honeypot(row.password),
        password_generated=row.password_generated,
    )


def ip_location(row: models.IpLocation) -> IpLocation:
    return IpLocation(
        country_code=row.country_code,
        city=row.city,
        latitude=row.latitude,
        longitude=row.longitude,
        asn=row.asn,
        as_organisation=row.as_organisation,
        source=row.source,
        located_at=row.located_at,
    )


async def fetch_locations(
    conn: AsyncConnection, addresses: Iterable[str]
) -> dict[str, IpLocation]:
    """The locations of those `addresses` that were located, by address."""
    rows = await queries.get_ip_locations(conn, ip_addresses=sorted(set(addresses)))
    return {row.ip_address: ip_location(row) for row in rows}


def ip_summary(
    row: queries.GetIpActivityRow | None,
    location: IpLocation | None,
    ban: queries.GetActiveIpBanRow | None,
) -> IpSummary:
    """`row` is None for an address that did nothing, `ban` for one that isn't banned."""
    public_ban = None if ban is None else Ban(since=ban.added, until=ban.expires)
    if row is None:
        return IpSummary(
            requests=0,
            distinct_paths=0,
            login_attempts=0,
            install_attempts=0,
            banned_requests=0,
            first_seen_at=None,
            last_seen_at=None,
            location=location,
            ban=public_ban,
        )
    return IpSummary(
        requests=row.requests,
        distinct_paths=row.distinct_paths,
        login_attempts=row.login_attempts,
        install_attempts=row.install_attempts,
        banned_requests=row.banned_requests,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        location=location,
        ban=public_ban,
    )


def ids_of(kind: EventKind, page: Sequence[ListedEvent]) -> list[int]:
    return [row.id_ for row in page if row.kind == kind]


def in_page_order(page: Sequence[ListedEvent], events: Iterable[Event]) -> list[Event]:
    """`events` in the page's order. An event deleted between the two steps is left out."""
    by_key = {(event.kind, event.id): event for event in events}
    return [by_key[key] for row in page if (key := (row.kind, row.id_)) in by_key]


async def fetch_events(
    conn: AsyncConnection, page: Sequence[ListedEvent]
) -> list[Event]:
    """The details of a page of listed events, in the page's order. Only the kinds on the
    page are queried."""
    events: list[Event] = []
    if ids := ids_of(EventKind.HIT, page):
        events += map(hit_event, await queries.get_hits_by_ids(conn, ids=ids))
    if ids := ids_of(EventKind.LOGIN_ATTEMPT, page):
        events += map(
            login_attempt_event,
            await queries.get_login_attempts_by_ids(conn, ids=ids),
        )
    if ids := ids_of(EventKind.INSTALL_ATTEMPT, page):
        events += map(
            install_attempt_event,
            await queries.get_install_attempts_by_ids(conn, ids=ids),
        )
    return in_page_order(page, events)


# The most logins one takeover lists; the rest are counted.
TAKEOVER_MAX_LOGINS = 200


async def fetch_takeover(conn: AsyncConnection, install_id: int) -> Takeover | None:
    """The install `install_id` and the logins into its account; None if there is no such
    install."""
    installs = await queries.get_install_attempts_by_ids(conn, ids=[install_id])
    if not installs:
        return None
    install = install_attempt_event(installs[0])
    ids = await queries.list_install_login_ids(
        conn, install_id=install_id, max_rows=TAKEOVER_MAX_LOGINS
    )
    logins = sorted(
        map(
            login_attempt_event, await queries.get_login_attempts_by_ids(conn, ids=ids)
        ),
        key=lambda login: (login.occurred_at, login.id),
    )
    return Takeover(
        install=install,
        logins=logins,
        login_count=await queries.count_install_logins(conn, install_id=install_id)
        or 0,
        locations=await fetch_locations(
            conn, {install.ip_address, *(login.ip_address for login in logins)}
        ),
    )
