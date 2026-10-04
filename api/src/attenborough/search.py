"""The exhibit's search: a query such as `country:RU,CN path:/wp-* -method:GET date:>=2026-09-01`,
parsed here and run as one database query (queries.sql, SearchEvents).

A query is terms separated by spaces, and an event must match every term. A term is `field:value`
(FIELDS lists the fields). Commas separate values, any of which may match, and so does repeating a
field. A leading `-` turns a term around: the event must match none of its values. Quote a value
that holds spaces, commas or backslashes, as in a shell: `user_agent:"*KHTML, like Gecko*"`.

Text matches whole, ignoring case, with `*` for any run of characters and `?` for any one: `/wp-*`.
Counts and times also take ranges: `>N`, `>=N`, `<N`, `<=N` and `N..M` (both ends included). A
time is a day, `2026-09-01`, or a minute, `2026-09-01T14:30`, in UTC; a day as a value means the
whole day. A bare address or network, without a field, means `ip:`.
"""

import shlex
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from http import HTTPMethod
from ipaddress import ip_network
from typing import Final

from psycopg import AsyncConnection
from pydantic_core import PydanticCustomError

from attenborough import events
from attenborough.db import queries
from attenborough.db.enums import EventKind, PathCategory


class SearchField(StrEnum):
    """What a search term can name. The names a response rule's markers share (rules.py) mean the
    same here."""

    IP = "ip"
    DATE = "date"
    KIND = "kind"
    COUNTRY = "country"
    CITY = "city"
    ASN = "asn"
    NETWORK = "network"
    REQUESTS = "requests"
    LOGINS = "logins"
    FIRST_SEEN = "first_seen"
    LAST_SEEN = "last_seen"
    METHOD = "method"
    PATH = "path"
    QUERY = "query"
    USER_AGENT = "user_agent"
    STATUS = "status"
    CATEGORY = "category"
    BANNED = "banned"
    USERNAME = "username"
    PASSWORD = "password"


# Every field, and what it matches: the exhibit's help shows these, and the search box completes
# them. src/tests/test_search.py checks every field is described.
FIELDS: dict[SearchField, str] = {
    SearchField.IP: "The visitor's address, or any address in a network: 203.0.113.0/24.",
    SearchField.DATE: "When it happened: 2026-09-01 (all day), >=2026-09-01T14:30, 2026-09-01..2026-09-07.",
    SearchField.KIND: "What happened: hit (a request), login_attempt or install_attempt.",
    SearchField.COUNTRY: "The address's country, as an ISO code: RU, CN. DB-IP's estimate.",
    SearchField.CITY: "The address's city: frankfurt*. DB-IP's estimate.",
    SearchField.ASN: "The number of the network the address is in: 14061.",
    SearchField.NETWORK: "Who runs that network: *digitalocean*.",
    SearchField.REQUESTS: "How many requests the address sent in all: >1000.",
    SearchField.LOGINS: "How many logins the address tried in all: >=20.",
    SearchField.FIRST_SEEN: "When the address sent its first request: >=2026-09-01.",
    SearchField.LAST_SEEN: "When the address sent its latest request: <2026-09-01.",
    SearchField.METHOD: "The request's method: POST.",
    SearchField.PATH: "The path, without the query: *.env, /wp-content/*. Logins have one too.",
    SearchField.QUERY: 'The query after "?": *cmd=*.',
    SearchField.USER_AGENT: 'The User-Agent header: *zgrab*, or "" for none.',
    SearchField.STATUS: "The status the honeypot answered with: 404.",
    SearchField.CATEGORY: "What the path was after, the exhibit's guess from the path: secrets.",
    SearchField.BANNED: "Whether the request was refused because its address was banned: true.",
    SearchField.USERNAME: "The username a login or install attempt gave: admin.",
    SearchField.PASSWORD: "The password a login or install attempt gave: *123*.",
}

# Fields only requests have, and fields only login and install attempts have: a term on one leaves
# out the events without it.
_HIT_FIELDS = frozenset(
    {
        SearchField.METHOD,
        SearchField.QUERY,
        SearchField.USER_AGENT,
        SearchField.STATUS,
        SearchField.CATEGORY,
        SearchField.BANNED,
    }
)
_ATTEMPT_FIELDS = frozenset({SearchField.USERNAME, SearchField.PASSWORD})
# Fields about the address, rather than the event: SearchAddresses selects those addresses first.
_ADDRESS_FIELDS = frozenset(
    {
        SearchField.IP,
        SearchField.COUNTRY,
        SearchField.CITY,
        SearchField.ASN,
        SearchField.NETWORK,
        SearchField.REQUESTS,
        SearchField.LOGINS,
        SearchField.FIRST_SEEN,
        SearchField.LAST_SEEN,
    }
)

_TRUE = "true"
_FALSE = "false"
_BOOLEANS = {_TRUE: True, _FALSE: False}


def suggestions(country_codes: Iterable[str]) -> dict[SearchField, list[str]]:
    """The values the search box suggests for each field with few of them."""
    return {
        SearchField.KIND: list(EventKind),
        SearchField.CATEGORY: list(PathCategory),
        SearchField.METHOD: list(HTTPMethod),
        SearchField.BANNED: list(_BOOLEANS),
        SearchField.COUNTRY: list(country_codes),
    }


class SearchError(ValueError):
    """A query that can't be searched, with a message for the reader."""


_NEGATION = "-"
_FIELD_SEPARATOR = ":"
_VALUE_SEPARATOR = ","
_RANGE_SEPARATOR = ".."
# Glob to LIKE: LIKE's own wildcards and escape character are escaped, then the glob's become them.
_LIKE = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_", "*": "%", "?": "_"})
_MAX_ASN = 2**32 - 1
_MIN_STATUS = 100
_MAX_STATUS = 599
_DAY_FORMAT = "%Y-%m-%d"
_MINUTE_FORMAT = "%Y-%m-%dT%H:%M"
_SPANS = ((_DAY_FORMAT, timedelta(days=1)), (_MINUTE_FORMAT, timedelta(minutes=1)))


def _like(glob: str) -> str:
    return glob.translate(_LIKE)


def _network(value: str) -> str:
    try:
        return str(ip_network(value, strict=False))
    except ValueError:
        raise SearchError(f'"{value}" is not an address or a network.') from None


def _country(value: str) -> str:
    code = value.upper()
    if len(code) != 2 or not code.isascii() or not code.isalpha():
        raise SearchError(f'"{value}" is not a two-letter country code, such as RU.')
    return code


def _number(value: str, low: int, high: int) -> int:
    if not value.isdecimal() or not low <= int(value) <= high:
        raise SearchError(f'"{value}" is not a number from {low} to {high}.')
    return int(value)


def _asn(value: str) -> int:
    return _number(value, 0, _MAX_ASN)


def _status(value: str) -> int:
    return _number(value, _MIN_STATUS, _MAX_STATUS)


def _choice[E: StrEnum](choices: type[E]) -> Callable[[str], E]:
    def parse(value: str) -> E:
        try:
            return choices(value.lower())
        except ValueError:
            names = ", ".join(choices)
            raise SearchError(f'"{value}" is not one of {names}.') from None

    return parse


def _count_span(value: str) -> tuple[int, int]:
    """The counts `value` names, as [start, stop)."""
    count = _number(value, 0, events.MAX_ID - 1)
    return count, count + 1


def _time_span(value: str) -> tuple[datetime, datetime]:
    """The times `value` names, as [start, stop): a day or a minute, in UTC."""
    for time_format, length in _SPANS:
        try:
            start = datetime.strptime(value, time_format).replace(tzinfo=UTC)
        except ValueError:
            continue
        return start, start + length
    raise SearchError(
        f'"{value}" is not a day (2026-09-01) or a minute (2026-09-01T14:30).'
    )


class _Comparison(StrEnum):
    # Longest first: `>=` must be tried before `>`.
    AT_LEAST = ">="
    AT_MOST = "<="
    MORE = ">"
    LESS = "<"


def _bounds[T](
    value: str, span: Callable[[str], tuple[T, T]]
) -> tuple[T | None, T | None]:
    """The range `value` names, as [start, stop), either end open (None)."""
    for comparison in _Comparison:
        if value.startswith(comparison):
            start, stop = span(value.removeprefix(comparison))
            match comparison:
                case _Comparison.AT_LEAST:
                    return start, None
                case _Comparison.MORE:
                    return stop, None
                case _Comparison.AT_MOST:
                    return None, stop
                case _Comparison.LESS:
                    return None, start
    first, separator, last = value.partition(_RANGE_SEPARATOR)
    if separator:
        return span(first)[0], span(last)[1]
    return span(value)


@dataclass
class Matches[T]:
    """One field's values: an event matches if it has any of `include` (or there are none), and
    none of `exclude`."""

    include: list[T] = field(default_factory=list[T])
    exclude: list[T] = field(default_factory=list[T])

    def add(self, values: Iterable[T], negated: bool) -> None:
        (self.exclude if negated else self.include).extend(values)


@dataclass
class Range[T: (int, datetime)]:
    """One field's range, [start, stop), either end open (None). Each term narrows it."""

    start: T | None = None
    stop: T | None = None

    def narrow(self, bounds: tuple[T | None, T | None]) -> None:
        start, stop = bounds
        if start is not None and (self.start is None or start > self.start):
            self.start = start
        if stop is not None and (self.stop is None or stop < self.stop):
            self.stop = stop


@dataclass(frozen=True)
class _Term:
    negated: bool
    field: SearchField
    values: list[str]


def _terms(query: str) -> list[_Term]:
    """The query's terms, with commas joining values (and quotes removed), as a shell splits
    words."""
    lexer = shlex.shlex(query, posix=True, punctuation_chars=_VALUE_SEPARATOR)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        raise SearchError("A quote is never closed.") from None
    terms: list[_Term] = []
    continued = False
    for token in tokens:
        if not token.strip(_VALUE_SEPARATOR):
            continued = bool(terms)
        elif continued:
            terms[-1].values.append(token)
            continued = False
        else:
            terms.append(_term(token))
    return terms


def _term(token: str) -> _Term:
    negated = token.startswith(_NEGATION)
    text = token.removeprefix(_NEGATION)
    name, separator, value = text.partition(_FIELD_SEPARATOR)
    if separator and name in SearchField:
        return _Term(negated, SearchField(name), [value])
    try:
        _ = ip_network(text, strict=False)
    except ValueError:
        pass
    else:
        return _Term(negated, SearchField.IP, [text])
    if separator:
        raise SearchError(f'There is no field "{name}". See the help for every field.')
    raise SearchError(f'"{text}" needs a field, such as {SearchField.PATH}:{text}.')


@dataclass
class Search:
    """A parsed query: each field's values, as SearchEvents takes them."""

    fields: set[SearchField] = field(default_factory=set[SearchField])
    ips: Matches[str] = field(default_factory=Matches[str])
    kinds: Matches[EventKind] = field(default_factory=Matches[EventKind])
    countries: Matches[str] = field(default_factory=Matches[str])
    cities: Matches[str] = field(default_factory=Matches[str])
    asns: Matches[int] = field(default_factory=Matches[int])
    networks: Matches[str] = field(default_factory=Matches[str])
    methods: Matches[str] = field(default_factory=Matches[str])
    paths: Matches[str] = field(default_factory=Matches[str])
    queries: Matches[str] = field(default_factory=Matches[str])
    user_agents: Matches[str] = field(default_factory=Matches[str])
    statuses: Matches[int] = field(default_factory=Matches[int])
    categories: Matches[PathCategory] = field(default_factory=Matches[PathCategory])
    usernames: Matches[str] = field(default_factory=Matches[str])
    passwords: Matches[str] = field(default_factory=Matches[str])
    banned: bool | None = None
    date: Range[datetime] = field(default_factory=Range[datetime])
    requests: Range[int] = field(default_factory=Range[int])
    logins: Range[int] = field(default_factory=Range[int])
    first_seen: Range[datetime] = field(default_factory=Range[datetime])
    last_seen: Range[datetime] = field(default_factory=Range[datetime])

    @classmethod
    def parse(cls, query: str) -> Search:
        """Raises SearchError, naming the term, if `query` can't be searched."""
        search = cls()
        for term in _terms(query):
            try:
                search.add(term)
            except SearchError as exc:
                raise SearchError(f"{term.field}: {exc}") from None
            search.fields.add(term.field)
        return search

    def add(self, term: _Term) -> None:
        values, negated = term.values, term.negated
        match term.field:
            case SearchField.IP:
                self.ips.add(map(_network, values), negated)
            case SearchField.KIND:
                self.kinds.add(map(_choice(EventKind), values), negated)
            case SearchField.COUNTRY:
                self.countries.add(map(_country, values), negated)
            case SearchField.CITY:
                self.cities.add(map(_like, values), negated)
            case SearchField.ASN:
                self.asns.add(map(_asn, values), negated)
            case SearchField.NETWORK:
                self.networks.add(map(_like, values), negated)
            case SearchField.METHOD:
                self.methods.add(map(_like, values), negated)
            case SearchField.PATH:
                self.paths.add(map(_like, values), negated)
            case SearchField.QUERY:
                self.queries.add(map(_like, values), negated)
            case SearchField.USER_AGENT:
                self.user_agents.add(map(_like, values), negated)
            case SearchField.STATUS:
                self.statuses.add(map(_status, values), negated)
            case SearchField.CATEGORY:
                self.categories.add(map(_choice(PathCategory), values), negated)
            case SearchField.USERNAME:
                self.usernames.add(map(_like, values), negated)
            case SearchField.PASSWORD:
                self.passwords.add(map(_like, values), negated)
            case SearchField.BANNED:
                self.add_banned(values, negated)
            case SearchField.DATE:
                self.date.narrow(_range(term, _time_span))
            case SearchField.REQUESTS:
                self.requests.narrow(_range(term, _count_span))
            case SearchField.LOGINS:
                self.logins.narrow(_range(term, _count_span))
            case SearchField.FIRST_SEEN:
                self.first_seen.narrow(_range(term, _time_span))
            case SearchField.LAST_SEEN:
                self.last_seen.narrow(_range(term, _time_span))

    def add_banned(self, values: list[str], negated: bool) -> None:
        if len(values) != 1 or values[0].lower() not in _BOOLEANS:
            raise SearchError(f"Write {_TRUE} or {_FALSE}.")
        banned = _BOOLEANS[values[0].lower()] != negated
        if self.banned is not None and self.banned != banned:
            raise SearchError(f"Write {_TRUE} or {_FALSE}, not both.")
        self.banned = banned

    def includes(self, kind: EventKind) -> bool:
        """Whether events of `kind` can match: the kind isn't left out, and has every field the
        search uses."""
        if self.kinds.include and kind not in self.kinds.include:
            return False
        if kind in self.kinds.exclude:
            return False
        if kind == EventKind.HIT:
            return not self.fields & _ATTEMPT_FIELDS
        return not self.fields & _HIT_FIELDS

    async def run(
        self, conn: AsyncConnection, cursor: events.EventCursor, limit: int
    ) -> Sequence[queries.SearchEventsRow]:
        """Up to `limit` matching events after `cursor`, newest first. Call it inside a transaction
        configured for searching (queries.sql, ConfigureSearch)."""
        by_address = bool(self.fields & _ADDRESS_FIELDS)
        addresses: Sequence[str] = []
        if by_address:
            addresses = await self.addresses(conn)
            if not addresses:
                return []
        return await queries.search_events(
            conn,
            before_at=cursor.occurred_at,
            before_kind=cursor.kind,
            before_id=cursor.id,
            limit=limit,
            honeypot=events.HONEYPOT.pattern,
            placeholder=events.HONEYPOT_PLACEHOLDER,
            include_hits=self.includes(EventKind.HIT),
            include_logins=self.includes(EventKind.LOGIN_ATTEMPT),
            include_installs=self.includes(EventKind.INSTALL_ATTEMPT),
            by_address=by_address,
            addresses=addresses,
            from_at=self.date.start,
            to_at=self.date.stop,
            methods=self.methods.include,
            not_methods=self.methods.exclude,
            paths=self.paths.include,
            not_paths=self.paths.exclude,
            queries=self.queries.include,
            not_queries=self.queries.exclude,
            user_agents=self.user_agents.include,
            not_user_agents=self.user_agents.exclude,
            statuses=self.statuses.include,
            not_statuses=self.statuses.exclude,
            categories=self.categories.include,
            not_categories=self.categories.exclude,
            banned=self.banned,
            usernames=self.usernames.include,
            not_usernames=self.usernames.exclude,
            passwords=self.passwords.include,
            not_passwords=self.passwords.exclude,
        )

    async def addresses(self, conn: AsyncConnection) -> Sequence[str]:
        """The addresses the search's address fields match."""
        # ponytail: every matching address goes to SearchEvents as one array, fine for the tens of
        # thousands ip_activity holds; past millions, join SearchAddresses into SearchEvents instead.
        return await queries.search_addresses(
            conn,
            ips=self.ips.include,
            not_ips=self.ips.exclude,
            countries=self.countries.include,
            not_countries=self.countries.exclude,
            cities=self.cities.include,
            not_cities=self.cities.exclude,
            asns=self.asns.include,
            not_asns=self.asns.exclude,
            networks=self.networks.include,
            not_networks=self.networks.exclude,
            requests_from=self.requests.start,
            requests_to=self.requests.stop,
            logins_from=self.logins.start,
            logins_to=self.logins.stop,
            first_seen_from=self.first_seen.start,
            first_seen_to=self.first_seen.stop,
            last_seen_from=self.last_seen.start,
            last_seen_to=self.last_seen.stop,
        )


def _range[T: (int, datetime)](
    term: _Term, span: Callable[[str], tuple[T, T]]
) -> tuple[T | None, T | None]:
    if term.negated:
        raise SearchError("A range can't be negated: write the opposite range instead.")
    if len(term.values) != 1:
        raise SearchError("Write one range, such as >=10 or 10..20.")
    return _bounds(term.values[0], span)


# The 422's error type, and its message: the reason, as is.
_QUERY_ERROR: Final = "search"
_QUERY_REASON: Final = "reason"
_QUERY_MESSAGE: Final = "{reason}"


def valid_query(query: str) -> str:
    """Rejects (422, with the reason as its message) a query that can't be searched."""
    try:
        _ = Search.parse(query)
    except SearchError as exc:
        raise PydanticCustomError(
            _QUERY_ERROR, _QUERY_MESSAGE, {_QUERY_REASON: str(exc)}
        ) from None
    return query
