"""Response rules: what the decoy answers instead of its own page, written by an admin (admin.py).

Before serving each request, the decoy asks the API (ingest.py, judge_visit). The first active rule,
in order, whose method, path pattern and condition match answers it instead: its status, headers
and body. The condition, header values and body are Liquid templates (python-liquid2), with the
same markers: facts about the visitor, the request as sent, the time, and a fresh canary. Nothing a
visitor sends is ever run: Liquid only reads the markers, under limits on loops and output, and
HTML bodies escape every marker. The decoy only serves what this module rendered.
"""

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from fnmatch import fnmatchcase
from functools import lru_cache
from http import HTTPMethod
from typing import ClassVar, Self

from liquid2 import Environment, StrictUndefined, Template
from liquid2.exceptions import LiquidError
from psycopg import AsyncConnection
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, model_validator

from attenborough import canaries
from attenborough.db import queries

logger = logging.getLogger(__name__)

# The longest a rule may make the visitor wait: under nginx's 60 s proxy timeout, like the tarpit.
MAX_DELAY_MS = 15_000
MIN_STATUS = 200
MAX_STATUS = 599
# Statuses whose responses have no body (RFC 9110).
_BODYLESS_STATUSES = frozenset({204, 205, 304})
# The window of the `logins_10m` marker.
_LOGINS_WINDOW = timedelta(minutes=10)
# A response header's name: an HTTP token.
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
# What a rendered header value may not contain: it would end the header.
_HEADER_BREAKS = re.compile(r"[\r\n\0]")
# Headers the decoy's server sets itself, or that the rule sets through content_type.
_RESERVED_HEADERS = frozenset(
    {
        "content-length",
        "transfer-encoding",
        "connection",
        "content-type",
        "x-content-type-options",
    }
)
# Media types whose bodies a browser never runs (with nosniff, below): the only ones whose markers
# are not HTML-escaped, so JSON can quote them with `| json`. Every other type (HTML, XML, SVG,
# anything unknown) escapes every marker, so nothing a visitor sent can become markup or script.
_INERT_TYPES = frozenset({"text/plain", "application/json"})
_JSON_SUFFIX = "+json"
# Sent with every rule's answer, so a browser takes the content type as given and never sniffs a
# text or JSON body as HTML.
_NOSNIFF = {"X-Content-Type-Options": "nosniff"}
_CONTENT_TYPE_SEPARATOR = ";"
# The condition is rendered inside this `if`: a match renders the marker.
_MATCHED = "1"
_MAX_RULE_TEXT = 4096
MAX_PREVIEW_PATH = _MAX_RULE_TEXT
_MAX_BODY = 256 * 1024
_MAX_HEADERS = 20
_MAX_NOTE = 1000
_MAX_METHOD = 32
_MAX_CONTENT_TYPE = 200
_DEFAULT_CONTENT_TYPE = "text/html; charset=UTF-8"
# Used in previews and in the check on save, instead of issuing a real canary.
SAMPLE_CANARY = "SampleCanary0000000000000"
_SAMPLE_IP = "203.0.113.7"
# The site's root, a sample request's and a preview's path.
ROOT_PATH = "/"


class Marker(StrEnum):
    """The names a rule's templates can use (MARKERS says what each holds)."""

    IP = "ip"
    COUNTRY = "country"
    CITY = "city"
    ASN = "asn"
    NETWORK = "network"
    FIRST_SEEN = "first_seen"
    REQUESTS = "requests"
    LOGINS_10M = "logins_10m"
    HAS_CANARY = "has_canary"
    BANNED_BEFORE = "banned_before"
    METHOD = "method"
    PATH = "path"
    QUERY = "query"
    USER_AGENT = "user_agent"
    HEADERS = "headers"
    NOW = "now"
    CANARY = "canary"


# Every marker, and what it holds: the same in conditions, header values and bodies. The admin
# area shows these, and the editor completes them; src/tests/test_rules.py checks that context()
# gives exactly these.
MARKERS: dict[Marker, str] = {
    Marker.IP: "The visitor's address.",
    Marker.COUNTRY: 'Its country (ISO code, e.g. "RU"), "" if unknown. DB-IP\'s estimate.',
    Marker.CITY: 'Its city, "" if unknown. DB-IP\'s estimate.',
    Marker.ASN: "The number of the network it is in (e.g. 14061), 0 if unknown.",
    Marker.NETWORK: 'Who runs that network (e.g. "DIGITALOCEAN-ASN"), "" if unknown.',
    Marker.FIRST_SEEN: "When it first sent the honeypot a request (now, on its first). Use | date.",
    Marker.REQUESTS: "How many requests it has sent the honeypot.",
    Marker.LOGINS_10M: "How many logins it tried in the last 10 minutes.",
    Marker.HAS_CANARY: "Whether it was ever handed a canary.",
    Marker.BANNED_BEFORE: "Whether it was ever banned.",
    Marker.METHOD: 'The request\'s method, e.g. "POST".',
    Marker.PATH: "The request's path, as sent, without the query.",
    Marker.QUERY: 'The query after "?", as sent, "" if none.',
    Marker.USER_AGENT: 'Its User-Agent header, "" if none.',
    Marker.HEADERS: 'Every header it sent, by lower-case name: headers["referer"].',
    Marker.NOW: "The time now (UTC). Use | date.",
    Marker.CANARY: "A fresh canary, recorded against the visitor (bodies and header values only).",
}

_headers = TypeAdapter(dict[str, str])
_USER_AGENT = "user-agent"
_NOTHING_KNOWN = queries.GetVisitorFactsRow(
    country_code=None,
    city=None,
    asn=None,
    as_organisation=None,
    requests=None,
    first_seen_at=None,
    logins=0,
    has_canary=False,
    banned_before=False,
)


class _Liquid(Environment):
    """Liquid with limits, so no template can make a response large or slow. A marker that doesn't
    exist is an error, so a typo is refused on save rather than silently never matching."""

    loop_iteration_limit: ClassVar[int | None] = 10_000
    local_namespace_limit: ClassVar[int | None] = 64 * 1024
    output_stream_limit: ClassVar[int | None] = 64 * 1024


_escaping = _Liquid(auto_escape=True, undefined=StrictUndefined)
_text = _Liquid(undefined=StrictUndefined)


def _escapes(content_type: str) -> bool:
    """Whether a body of `content_type` HTML-escapes its markers: all but the inert types."""
    media_type = content_type.split(_CONTENT_TYPE_SEPARATOR, 1)[0].strip().lower()
    return not (media_type in _INERT_TYPES or media_type.endswith(_JSON_SUFFIX))


@lru_cache(maxsize=1024)
def _template(source: str, escaped: bool) -> Template:
    """A template parsed once: rules are read on every request, but rarely change."""
    return (_escaping if escaped else _text).from_string(source)


def _condition(source: str) -> Template:
    return _template(f"{{% if {source} %}}{_MATCHED}{{% endif %}}", False)


@dataclass(frozen=True)
class Rule:
    """What a rule says, from the database or from the admin's form."""

    method: str | None
    path_pattern: str | None
    condition: str
    status_code: int
    content_type: str
    headers: Mapping[str, str]
    body: str
    delay_ms: int

    def matches_request(self, method: str, path: str) -> bool:
        return (self.method is None or self.method == method) and (
            self.path_pattern is None or fnmatchcase(path, self.path_pattern)
        )

    def holds(self, context: Mapping[str, object]) -> bool:
        """Whether the condition is true for these markers; a blank one always is."""
        if not self.condition.strip():
            return True
        return _condition(self.condition).render(**context) == _MATCHED

    def templates(self) -> list[Template]:
        escaped = _escapes(self.content_type)
        return [_template(self.body, escaped)] + [
            _template(value, False) for value in self.headers.values()
        ]

    def uses_canary(self) -> bool:
        return any(Marker.CANARY in t.global_variables() for t in self.templates())

    def render(self, context: Mapping[str, object]) -> RenderedResponse:
        headers = {
            name: _HEADER_BREAKS.sub("", _template(value, False).render(**context))
            for name, value in self.headers.items()
        } | _NOSNIFF
        body = _template(self.body, _escapes(self.content_type)).render(**context)
        return RenderedResponse(
            status_code=self.status_code,
            content_type=self.content_type,
            headers=headers,
            body=body,
            delay_ms=self.delay_ms,
        )


class RenderedResponse(BaseModel):
    """What the decoy serves instead of its own page."""

    status_code: int
    content_type: str
    headers: dict[str, str]
    body: str
    delay_ms: int


class RuleForm(BaseModel):
    """A rule as the admin writes it. Refused (422, with Liquid's message) unless every template
    parses and renders for a sample visitor."""

    # Blank: any method.
    method: str | None = Field(default=None, max_length=_MAX_METHOD)
    # Matched against the path as sent, without the query: exact, or a glob (`*`, `?`, `[...]`).
    # Blank: any path.
    path_pattern: str | None = Field(default=None, max_length=_MAX_RULE_TEXT)
    # A Liquid expression, as inside `{% if ... %}`. Blank: every visitor.
    condition: str = Field(default="", max_length=_MAX_RULE_TEXT)
    status_code: int = Field(default=200, ge=MIN_STATUS, le=MAX_STATUS)
    content_type: str = Field(
        default=_DEFAULT_CONTENT_TYPE, max_length=_MAX_CONTENT_TYPE
    )
    # Values are Liquid templates.
    headers: dict[str, str] = Field(default_factory=dict, max_length=_MAX_HEADERS)
    body: str = Field(default="", max_length=_MAX_BODY)
    delay_ms: int = Field(default=0, ge=0, le=MAX_DELAY_MS)
    # Null: until removed.
    expires: AwareDatetime | None = None
    # Private, like a ban's reason.
    note: str | None = Field(default=None, max_length=_MAX_NOTE)

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.method is not None:
            self.method = self.method.strip().upper() or None
        if self.path_pattern is not None:
            self.path_pattern = self.path_pattern.strip() or None
        if _HEADER_BREAKS.search(self.content_type):
            raise ValueError("The content type must be one line.")
        for name in self.headers:
            if not _HEADER_NAME.fullmatch(name):
                raise ValueError(f"{name!r} is not a header name.")
            if name.lower() in _RESERVED_HEADERS:
                raise ValueError(
                    f"{name} is set by the server (or by the content type)."
                )
        if self.status_code in _BODYLESS_STATUSES and self.body:
            raise ValueError(f"A {self.status_code} response has no body.")
        rule = self.rule()
        try:
            _ = rule.holds(sample_context())
        except LiquidError as exc:
            raise ValueError(f"Condition: {exc}") from exc
        try:
            _ = rule.render(sample_context())
        except LiquidError as exc:
            raise ValueError(f"Body or headers: {exc}") from exc
        return self

    def rule(self) -> Rule:
        return Rule(
            method=self.method,
            path_pattern=self.path_pattern,
            condition=self.condition,
            status_code=self.status_code,
            content_type=self.content_type,
            headers=self.headers,
            body=self.body,
            delay_ms=self.delay_ms,
        )


@dataclass(frozen=True)
class Request:
    """The request the decoy is about to serve, as sent."""

    method: str
    path: str
    query: str | None
    headers: Mapping[str, str]


def context(
    ip_address: str,
    facts: queries.GetVisitorFactsRow | None,
    request: Request,
    now: datetime,
) -> dict[str, object]:
    """The markers. None is never one, so every filter and comparison works on every visitor:
    unknown text is "", an unknown network number 0, and a first visit was first seen now. `facts`
    is None for an address the honeypot knows nothing about yet."""
    known = facts or _NOTHING_KNOWN
    return {
        Marker.IP: ip_address,
        Marker.COUNTRY: known.country_code or "",
        Marker.CITY: known.city or "",
        Marker.ASN: known.asn or 0,
        Marker.NETWORK: known.as_organisation or "",
        Marker.FIRST_SEEN: known.first_seen_at or now,
        Marker.REQUESTS: known.requests or 0,
        Marker.LOGINS_10M: known.logins,
        Marker.HAS_CANARY: known.has_canary,
        Marker.BANNED_BEFORE: known.banned_before,
        Marker.METHOD: request.method,
        Marker.PATH: request.path,
        Marker.QUERY: request.query or "",
        Marker.USER_AGENT: request.headers.get(_USER_AGENT, ""),
        Marker.HEADERS: dict(request.headers),
        Marker.NOW: now,
    }


def sample_context() -> dict[str, object]:
    """Markers for a made-up visitor, to check a rule renders before it is saved."""
    request = Request(method=HTTPMethod.GET, path=ROOT_PATH, query=None, headers={})
    return {
        **context(_SAMPLE_IP, None, request, datetime.now(UTC)),
        Marker.CANARY: SAMPLE_CANARY,
    }


async def visitor_context(
    conn: AsyncConnection, ip_address: str, request: Request
) -> dict[str, object]:
    now = datetime.now(UTC)
    facts = await queries.get_visitor_facts(
        conn, ip_address=ip_address, logins_since=now - _LOGINS_WINDOW
    )
    return context(ip_address, facts, request, now)


def _active_rule(row: queries.ListActiveRulesRow) -> Rule:
    return Rule(
        method=row.method,
        path_pattern=row.path_pattern,
        condition=row.condition,
        status_code=row.status_code,
        content_type=row.content_type,
        headers=headers_from_json(row.headers),
        body=row.body,
        delay_ms=row.delay_ms,
    )


def headers_json(headers: Mapping[str, str]) -> str:
    return json.dumps(dict(headers))


def headers_from_json(headers: str) -> dict[str, str]:
    return _headers.validate_json(headers)


async def respond(
    conn: AsyncConnection, ip_address: str, request: Request
) -> tuple[int, RenderedResponse] | None:
    """The first matching rule's id and the response it gives this request, or None for the
    decoy's own.

    Facts about the visitor are only read when a rule's method and path match. A rule that fails
    to render (a resource limit) is logged and skipped.
    """
    candidates: Sequence[tuple[int, Rule]] = [
        (row.id_, rule)
        async for row in queries.list_active_rules(conn)
        if (rule := _active_rule(row)).matches_request(request.method, request.path)
    ]
    if not candidates:
        return None
    markers = await visitor_context(conn, ip_address, request)
    for rule_id, rule in candidates:
        try:
            if not rule.holds(markers):
                continue
            if rule.uses_canary():
                markers[Marker.CANARY] = await canaries.issue_canary(
                    conn, path=request.path, ip_address=ip_address
                )
            rendered = rule.render(markers)
        except LiquidError:
            logger.warning(
                "Response rule %d failed; skipping it", rule_id, exc_info=True
            )
            continue
        return rule_id, rendered
    return None
