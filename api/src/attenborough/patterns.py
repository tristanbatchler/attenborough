"""The Patterns page: what the honeypot's visitors are after, who they are, when they come, and the
tools and wordlists they use, in aggregate.

Figures over requests and login attempts cover the last WINDOW_DAYS days (whole UTC days, today
included), so what they cost is bounded by one week's traffic. Figures per address cover all time,
from running totals (queries.sql, "The Patterns page"). Every text a visitor sent goes through
hide_honeypot, as everywhere on the exhibit.

The page is public and its queries read many rows, so the figures are computed at most once every
REFRESH_INTERVAL and served from memory in between (`latest_patterns`).
"""

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, date, datetime, time, timedelta

from psycopg import AsyncConnection
from pydantic import BaseModel

from attenborough.db import queries
from attenborough.db.enums import PathCategory
from attenborough.events import hide_honeypot

WINDOW_DAYS = 7
REFRESH_INTERVAL = timedelta(minutes=5)
HOURS_PER_DAY = 24

TOP_PATHS = 20
TOP_USER_AGENTS = 10
TOP_CREDENTIALS = 15
TOP_COUNTRIES = 20
TOP_NETWORKS = 15
TOP_ADDRESSES = 10
TOP_TOOLKITS = 10
# A toolkit is a set of at least this many paths requested, exactly, by two or more addresses.
# Fewer would count every crawler that asks for / and /favicon.ico.
MIN_TOOLKIT_PATHS = 5
MAX_TOOLKIT_ADDRESSES = 12
TOOLKIT_EXAMPLE_PATHS = 8
MAP_PLACES = 1000


class Totals(BaseModel):
    """All time."""

    requests: int
    login_attempts: int
    install_attempts: int
    addresses: int
    # Distinct countries among the located addresses.
    countries: int
    # In the last 24 hours.
    requests_last_day: int
    # The first and last request to the honeypot; null before the first.
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class CategoryCount(BaseModel):
    category: PathCategory
    requests: int
    addresses: int


class PathCount(BaseModel):
    path: str
    category: PathCategory
    requests: int
    addresses: int


class UserAgentCount(BaseModel):
    # Null for requests that sent no User-Agent.
    user_agent: str | None
    requests: int
    addresses: int


class DayActivity(BaseModel):
    """One UTC day's requests, hour by hour (24 numbers, from 00:00)."""

    day: date
    requests_by_hour: list[int]


class CredentialCount(BaseModel):
    """A username or password, and how often it was tried."""

    value: str
    attempts: int
    addresses: int


class CountryCount(BaseModel):
    # Null for addresses that weren't located, or whose country isn't known.
    country_code: str | None
    requests: int
    addresses: int


class NetworkCount(BaseModel):
    # Null for addresses that weren't located, or whose network isn't known.
    asn: int | None
    as_organisation: str | None
    requests: int
    addresses: int


class AddressActivity(BaseModel):
    ip_address: str
    country_code: str | None
    requests: int
    distinct_paths: int
    login_attempts: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class Toolkit(BaseModel):
    """Addresses that each requested exactly the same set of paths: one tool, several machines."""

    paths: int
    address_count: int
    # The busiest of them, at most MAX_TOOLKIT_ADDRESSES.
    addresses: list[str]
    # Some of the paths, from one of the addresses.
    example_paths: list[str]


class MapPlace(BaseModel):
    """A place located addresses are in (DB-IP gives a city's coordinates)."""

    latitude: float
    longitude: float
    city: str | None
    country_code: str | None
    requests: int
    addresses: int


class Patterns(BaseModel):
    computed_at: datetime
    # The first moment the windowed figures (categories to passwords) count from.
    window_start: datetime
    totals: Totals
    categories: list[CategoryCount]
    paths: list[PathCount]
    user_agents: list[UserAgentCount]
    days: list[DayActivity]
    usernames: list[CredentialCount]
    passwords: list[CredentialCount]
    countries: list[CountryCount]
    networks: list[NetworkCount]
    busiest: list[AddressActivity]
    longest_seen: list[AddressActivity]
    toolkits: list[Toolkit]
    places: list[MapPlace]


def window_days(today: date) -> list[date]:
    """The window's days, oldest first, ending with `today`."""
    return [today - timedelta(days=n) for n in reversed(range(WINDOW_DAYS))]


def day_activity(
    days: list[date], rows: Iterable[queries.CountRequestsPerHourSinceRow]
) -> list[DayActivity]:
    """`rows` (one per hour with requests) laid out as `days` × 24 hours, zeros included."""
    counts = {row.hour: row.requests for row in rows}
    return [
        DayActivity(
            day=day,
            requests_by_hour=[
                counts.get(datetime.combine(day, time(hour), UTC), 0)
                for hour in range(HOURS_PER_DAY)
            ],
        )
        for day in days
    ]


def _credentials(
    rows: Iterable[queries.TopUsernamesSinceRow | queries.TopPasswordsSinceRow],
) -> list[CredentialCount]:
    return [
        CredentialCount(
            value=hide_honeypot(row.value),
            attempts=row.attempts,
            addresses=row.addresses,
        )
        for row in rows
    ]


def _address_activity(
    row: queries.BusiestAddressesRow | queries.LongestSeenAddressesRow,
) -> AddressActivity:
    return AddressActivity(
        ip_address=row.ip_address,
        country_code=row.country_code,
        requests=row.requests,
        distinct_paths=row.distinct_paths,
        login_attempts=row.login_attempts,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
    )


async def _toolkit(conn: AsyncConnection, row: queries.ListToolkitsRow) -> Toolkit:
    paths = await queries.list_paths_of(
        conn, ip_address=row.example_address, limit=TOOLKIT_EXAMPLE_PATHS
    )
    return Toolkit(
        paths=row.paths,
        address_count=row.address_count,
        addresses=list(row.addresses),
        example_paths=[hide_honeypot(path) for path in paths],
    )


async def compute_patterns(conn: AsyncConnection, now: datetime) -> Patterns:
    days = window_days(now.date())
    since = datetime.combine(days[0], time(), UTC)
    totals = await queries.get_pattern_totals(conn)
    span = await queries.get_observation_span(conn)
    last_day = await queries.count_requests_since(conn, since=now - timedelta(days=1))
    return Patterns(
        computed_at=now,
        window_start=since,
        totals=Totals(
            requests=0 if totals is None else totals.requests,
            login_attempts=0 if totals is None else totals.login_attempts,
            install_attempts=0 if totals is None else totals.install_attempts,
            addresses=0 if totals is None else totals.addresses,
            countries=0 if totals is None else totals.countries,
            requests_last_day=last_day or 0,
            first_seen_at=None if span is None else span.first_seen_at,
            last_seen_at=None if span is None else span.last_seen_at,
        ),
        categories=[
            CategoryCount(
                category=row.category, requests=row.requests, addresses=row.addresses
            )
            for row in await queries.count_categories_since(conn, since=since)
        ],
        paths=[
            PathCount(
                path=hide_honeypot(row.path),
                category=row.category,
                requests=row.requests,
                addresses=row.addresses,
            )
            for row in await queries.top_paths_since(conn, since=since, limit=TOP_PATHS)
        ],
        user_agents=[
            UserAgentCount(
                user_agent=None
                if row.user_agent is None
                else hide_honeypot(row.user_agent),
                requests=row.requests,
                addresses=row.addresses,
            )
            for row in await queries.top_user_agents_since(
                conn, since=since, limit=TOP_USER_AGENTS
            )
        ],
        days=day_activity(
            days, await queries.count_requests_per_hour_since(conn, since=since)
        ),
        usernames=_credentials(
            await queries.top_usernames_since(conn, since=since, limit=TOP_CREDENTIALS)
        ),
        passwords=_credentials(
            await queries.top_passwords_since(conn, since=since, limit=TOP_CREDENTIALS)
        ),
        countries=[
            CountryCount(
                country_code=row.country_code,
                requests=row.requests,
                addresses=row.addresses,
            )
            for row in await queries.top_countries(conn, limit=TOP_COUNTRIES)
        ],
        networks=[
            NetworkCount(
                asn=row.asn,
                as_organisation=row.as_organisation,
                requests=row.requests,
                addresses=row.addresses,
            )
            for row in await queries.top_networks(conn, limit=TOP_NETWORKS)
        ],
        busiest=[
            _address_activity(row)
            for row in await queries.busiest_addresses(conn, limit=TOP_ADDRESSES)
        ],
        longest_seen=[
            _address_activity(row)
            for row in await queries.longest_seen_addresses(conn, limit=TOP_ADDRESSES)
        ],
        toolkits=[
            await _toolkit(conn, row)
            for row in await queries.list_toolkits(
                conn,
                min_paths=MIN_TOOLKIT_PATHS,
                max_addresses=MAX_TOOLKIT_ADDRESSES,
                limit=TOP_TOOLKITS,
            )
        ],
        places=[
            MapPlace(
                latitude=row.latitude,
                longitude=row.longitude,
                city=row.city,
                country_code=row.country_code,
                requests=row.requests,
                addresses=row.addresses,
            )
            for row in await queries.list_map_places(conn, limit=MAP_PLACES)
        ],
    )


class LatestPatterns:
    """The latest figures, recomputed by `compute` when they are REFRESH_INTERVAL old or more.

    Requests arriving while they are recomputed each compute them too: at most a few at once,
    with nginx limiting each reader's rate. Only one process serves the API (docker-compose.yml).
    """

    def __init__(
        self, compute: Callable[[AsyncConnection, datetime], Awaitable[Patterns]]
    ) -> None:
        self.compute: Callable[[AsyncConnection, datetime], Awaitable[Patterns]] = (
            compute
        )
        self.latest: Patterns | None = None

    async def get(self, conn: AsyncConnection, now: datetime) -> Patterns:
        if self.latest is None or now - self.latest.computed_at >= REFRESH_INTERVAL:
            self.latest = await self.compute(conn, now)
        return self.latest


latest_patterns = LatestPatterns(compute_patterns)
