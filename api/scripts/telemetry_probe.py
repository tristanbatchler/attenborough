"""Test and troubleshoot Attenborough request telemetry against a running server and its database.

Run from `api/` with the project environment, e.g. `uv run python scripts/telemetry_probe.py summary`.
It reaches the database through the app's own connection pool and `Settings` (`api/.env` plus
environment overrides), so it always inspects the same database as the server.

Subcommands:
  summary               Read-only overview of `telemetry_hits`: counts per group/status and probe rows.
  rows --run TAG        Read-only listing of the rows recorded for one probe run.
  verify --base-url URL Send a tagged request matrix (plus a concurrent burst) to a running server, then
                        check that every request produced exactly one row with the status the client
                        received, the expected router group and IP, and the path and query exactly as
                        sent. Exits 1 on any mismatch.
    --target decoy      Send them to the decoy app (decoy/) instead, which reports every request it
                        serves to the API's /ingest/hits: the same checks, end to end, plus the
                        body's size. Its matrix includes typical scanner traffic.

Every probe request carries `User-Agent: attenborough-probe/<run>` and a unique `x-probe: <run>-<n>-<label>`
header, so rows map one-to-one onto requests and test data can be identified later. `verify` writes real
rows to the configured database (telemetry, and through the decoy app login and install attempts);
the inspection commands only read.
"""

import argparse
import asyncio
import ipaddress
import sys
import time
from collections import Counter
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPMethod

import httpx
from psycopg import AsyncConnection
from psycopg.rows import class_row

from attenborough.db.enums import RouterGroup
from attenborough.db.ops import db_conn_pool
from attenborough.settings import get_settings
from attenborough.telemetry import USER_AGENT_HEADER

PROBE_USER_AGENT_PREFIX = "attenborough-probe/"
PROBE_HEADER = "x-probe"
PROBE_CREDENTIAL = "probe"
DEFAULT_API_URL = "http://127.0.0.1:8765"
DEFAULT_DECOY_URL = "http://127.0.0.1:8766"
DEFAULT_BURST = 100
RUN_OPTION = "--run"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
EXHIBIT_FEED_PATH = "/exhibit/feed?take=1"
OPENAPI_PATH = "/openapi.json"
NOT_FOUND_PATH = "/this/does/not/exist"
BURST_NOT_FOUND_PATH = "/burst/not/found"
WP_LOGIN_PATH = "/wp-login.php"
# WordPress's login form fields, as the decoy app's login page expects them.
WP_LOGIN_FORM = {"log": PROBE_CREDENTIAL, "pwd": PROBE_CREDENTIAL}
# WordPress's installer form (wp-admin/install.php, step 2), as a takeover bot submits it.
WP_INSTALL_FORM = {
    "weblog_title": PROBE_CREDENTIAL,
    "user_name": PROBE_CREDENTIAL,
    "admin_password": PROBE_CREDENTIAL,
    "admin_password2": PROBE_CREDENTIAL,
    "admin_email": "probe@example.com",
}
# A REST batch whose first path PHP can't parse, as the scanners seen in the field send it.
WP_BATCH_PROBE = {
    "requests": [
        {"method": "POST", "path": "http://:"},
        {"method": "DELETE", "path": "/wp/v2/categories/0"},
    ]
}
INDEX_PATH = "/index.php"
CONTENT_TYPE_HEADER = "Content-Type"
# The XML-RPC brute force scanners send WordPress: many logins in one system.multicall.
XMLRPC_MULTICALL = (
    b'<?xml version="1.0"?><methodCall><methodName>system.multicall</methodName><params>'
    + b"<param><value><array><data><value><struct><member><name>methodName</name><value>"
    + b"<string>wp.getUsersBlogs</string></value></member><member><name>params</name><value>"
    + b"<array><data><value><string>probe</string></value><value><string>probe</string></value>"
    + b"</data></array></value></member></struct></value></data></array></value></param>"
    + b"</params></methodCall>"
)
# More headers than a browser sends, fewer than Node's limit (maxHeadersCount 2000).
HEADER_FLOOD = {f"x-flood-{i}": str(i) for i in range(150)}
# Longer than nginx's default request-line limit (8 KiB), within Node's (16 KiB).
LONG_PATH = "/" + "a" * 9000
# The request line is compared one character per byte, as the servers record it.
REQUEST_LINE_ENCODING = "latin-1"
QUERY_SEPARATOR = "?"
DEFAULT_PEER_IP = "127.0.0.1"
FORWARDED_FOR_HEADER = "X-Forwarded-For"
REAL_IP_HEADER = "X-Real-IP"
TRUST_EVERY_PEER = "*"
# Documentation ranges (RFC 5737): a client-forged address, and the real client a proxy appends.
FORGED_IP = "198.51.100.66"
FORWARDED_CLIENT_IP = "203.0.113.7"


@dataclass(frozen=True)
class Case:
    label: str
    method: HTTPMethod
    path: str
    group: RouterGroup
    json: object = None
    form: dict[str, str] | None = None
    content: bytes | None = None
    headers: dict[str, str] = field(default_factory=dict[str, str])
    repeat: int = 1
    # Sent as a proxy chain "<forged>, <client>": only a trusted peer may make this the origin.
    forwarded_client: str | None = None


def request_matrix() -> list[Case]:
    """One case per outcome the telemetry must record identically: OK, framework errors
    (404/405/422), framework routes, and IP attribution. There is no unhandled-exception case,
    because nothing in the API deliberately crashes. The API's own honeypot traffic is anything
    that matches no route; its /ingest reports are never recorded, so they have no case here."""
    return [
        Case("exhibit-feed", HTTPMethod.GET, EXHIBIT_FEED_PATH, RouterGroup.EXHIBIT),
        Case(
            "exhibit-ip",
            HTTPMethod.GET,
            "/exhibit/ip/127.0.0.1/activity?take=1",
            RouterGroup.EXHIBIT,
        ),
        Case("root", HTTPMethod.GET, "/", RouterGroup.HONEYPOT),
        Case("404", HTTPMethod.GET, NOT_FOUND_PATH, RouterGroup.HONEYPOT),
        # The API doesn't capture bodies of the requests it serves: recorded as NULL.
        Case(
            "404-post",
            HTTPMethod.POST,
            NOT_FOUND_PATH,
            RouterGroup.HONEYPOT,
            form=WP_LOGIN_FORM,
        ),
        Case("405", HTTPMethod.DELETE, EXHIBIT_FEED_PATH, RouterGroup.EXHIBIT),
        # IP attribution: a client-set header must never choose the recorded origin.
        Case(
            "forged-x-real-ip",
            HTTPMethod.GET,
            NOT_FOUND_PATH,
            RouterGroup.HONEYPOT,
            headers={REAL_IP_HEADER: FORGED_IP},
        ),
        Case(
            "forwarded-chain",
            HTTPMethod.GET,
            NOT_FOUND_PATH,
            RouterGroup.HONEYPOT,
            forwarded_client=FORWARDED_CLIENT_IP,
        ),
        Case("docs", HTTPMethod.GET, "/docs", RouterGroup.SYSTEM),
        Case("openapi", HTTPMethod.GET, OPENAPI_PATH, RouterGroup.SYSTEM),
        # Rejected input (FastAPI validation, 422).
        Case(
            "invalid-ip",
            HTTPMethod.GET,
            "/exhibit/ip/not-an-ip/activity",
            RouterGroup.EXHIBIT,
        ),
        # A page cursor the API didn't make: rejected (422), never passed to the database.
        Case(
            "bad-cursor",
            HTTPMethod.GET,
            "/exhibit/ip/127.0.0.1/activity?before=not-a-cursor",
            RouterGroup.EXHIBIT,
        ),
    ]


def decoy_request_matrix() -> list[Case]:
    """The decoy app: every request it serves, whatever the outcome, is reported to the API and
    recorded as a honeypot hit, attributed to the visitor."""
    return [
        Case("decoy-page", HTTPMethod.GET, WP_LOGIN_PATH, RouterGroup.HONEYPOT),
        Case(
            "decoy-login",
            HTTPMethod.POST,
            WP_LOGIN_PATH,
            RouterGroup.HONEYPOT,
            form=WP_LOGIN_FORM,
        ),
        Case("decoy-404", HTTPMethod.GET, NOT_FOUND_PATH, RouterGroup.HONEYPOT),
        Case("decoy-delete", HTTPMethod.DELETE, WP_LOGIN_PATH, RouterGroup.HONEYPOT),
        Case("decoy-options", HTTPMethod.OPTIONS, WP_LOGIN_PATH, RouterGroup.HONEYPOT),
        # Scanner traffic: the row must keep the path, query and body exactly as sent.
        Case(
            "decoy-json-login",
            HTTPMethod.POST,
            WP_LOGIN_PATH,
            RouterGroup.HONEYPOT,
            json=WP_LOGIN_FORM,
        ),
        Case(
            "decoy-xmlrpc",
            HTTPMethod.POST,
            "/xmlrpc.php",
            RouterGroup.HONEYPOT,
            content=XMLRPC_MULTICALL,
            headers={CONTENT_TYPE_HEADER: "text/xml"},
        ),
        # A bot finishing the "unfinished" install: its admin account is recorded in the body.
        Case(
            "decoy-install",
            HTTPMethod.POST,
            "/wp-admin/install.php?step=2",
            RouterGroup.HONEYPOT,
            form=WP_INSTALL_FORM,
        ),
        # The batch-API probe scanners send, unparseable path first: WordPress's fatal error, a 500.
        Case(
            "decoy-batch",
            HTTPMethod.POST,
            "/?rest_route=/batch/v1",
            RouterGroup.HONEYPOT,
            json=WP_BATCH_PROBE,
        ),
        Case(
            "decoy-traversal",
            HTTPMethod.GET,
            "/cgi-bin/.%2e/.%2e/.%2e/.%2e/etc/passwd",
            RouterGroup.HONEYPOT,
        ),
        Case(
            "decoy-query",
            HTTPMethod.GET,
            f"{INDEX_PATH}?page=../../../../etc/passwd&id=1%27%20OR%20%271%27=%271",
            RouterGroup.HONEYPOT,
        ),
        Case(
            "decoy-empty-query",
            HTTPMethod.GET,
            f"{INDEX_PATH}{QUERY_SEPARATOR}",
            RouterGroup.HONEYPOT,
        ),
        Case("decoy-slash", HTTPMethod.GET, "/phpmyadmin/", RouterGroup.HONEYPOT),
        Case("decoy-long-path", HTTPMethod.GET, LONG_PATH, RouterGroup.HONEYPOT),
        Case(
            "decoy-header-flood",
            HTTPMethod.GET,
            WP_LOGIN_PATH,
            RouterGroup.HONEYPOT,
            headers=HEADER_FLOOD,
        ),
        # SvelteKit's own URLs, which must look like any other unknown path.
        Case(
            "decoy-sveltekit-data",
            HTTPMethod.GET,
            f"{WP_LOGIN_PATH}/__data.json",
            RouterGroup.HONEYPOT,
        ),
        Case(
            "decoy-sveltekit-app",
            HTTPMethod.GET,
            "/_app/version.json",
            RouterGroup.HONEYPOT,
        ),
        Case(
            "decoy-forged-x-real-ip",
            HTTPMethod.GET,
            WP_LOGIN_PATH,
            RouterGroup.HONEYPOT,
            headers={REAL_IP_HEADER: FORGED_IP},
        ),
        Case(
            "decoy-forwarded",
            HTTPMethod.GET,
            WP_LOGIN_PATH,
            RouterGroup.HONEYPOT,
            forwarded_client=FORWARDED_CLIENT_IP,
        ),
    ]


DECOY_BURST_CASES = [
    Case("decoy-burst-page", HTTPMethod.GET, WP_LOGIN_PATH, RouterGroup.HONEYPOT),
    Case(
        "decoy-burst-login",
        HTTPMethod.POST,
        WP_LOGIN_PATH,
        RouterGroup.HONEYPOT,
        form=WP_LOGIN_FORM,
    ),
    Case("decoy-burst-404", HTTPMethod.GET, BURST_NOT_FOUND_PATH, RouterGroup.HONEYPOT),
]


BURST_CASES = [
    Case("burst-feed", HTTPMethod.GET, EXHIBIT_FEED_PATH, RouterGroup.EXHIBIT),
    Case("burst-404", HTTPMethod.GET, BURST_NOT_FOUND_PATH, RouterGroup.HONEYPOT),
    Case("burst-openapi", HTTPMethod.GET, OPENAPI_PATH, RouterGroup.SYSTEM),
]


@dataclass(frozen=True)
class Sent:
    probe: str
    case: Case
    status: int
    # The request target (path and query) and body size, as httpx actually sent them.
    target: str
    body_size: int


@dataclass(frozen=True)
class HitRow:
    id: int
    probe: str | None
    ip: str
    method: str
    path: str
    query: str | None
    body_size: int | None
    router_group: str
    status_code: int
    occurred_at: datetime

    @property
    def target(self) -> str:
        """The request target as recorded: the path, then the query if there was a `?`."""
        if self.query is None:
            return self.path
        return f"{self.path}{QUERY_SEPARATOR}{self.query}"


@dataclass(frozen=True)
class GroupCount:
    router_group: str
    status_code: int
    hits: int
    first_seen: datetime
    last_seen: datetime


@dataclass(frozen=True)
class ProbeRunCount:
    user_agent: str
    hits: int
    first_seen: datetime


@asynccontextmanager
async def read_only_connection() -> AsyncGenerator[AsyncConnection]:
    """A connection from the app's pool whose session can only read: this tool inspects, and the
    server under test does all the writing. Needs the pool open (see `run`)."""
    async with db_conn_pool.connection() as conn:
        _ = await conn.execute("SET default_transaction_read_only = on")
        yield conn


async def fetch_run_rows(
    conn: AsyncConnection, run: str, since: datetime
) -> list[HitRow]:
    async with conn.cursor(row_factory=class_row(HitRow)) as cur:
        _ = await cur.execute(
            """
            SELECT id, headers->>%s AS probe, host(ip_address) AS ip, method, path, query,
                   body_size, router_group, status_code, occurred_at
            FROM telemetry_hits
            WHERE occurred_at >= %s AND user_agent = %s
            ORDER BY id
            """,
            (PROBE_HEADER, since, PROBE_USER_AGENT_PREFIX + run),
        )
        return await cur.fetchall()


async def summary() -> int:
    async with read_only_connection() as conn:
        async with conn.cursor(row_factory=class_row(GroupCount)) as cur:
            _ = await cur.execute(
                """
                SELECT router_group, status_code, count(*) AS hits,
                       min(occurred_at) AS first_seen, max(occurred_at) AS last_seen
                FROM telemetry_hits GROUP BY 1, 2 ORDER BY 1, 2
                """
            )
            groups = await cur.fetchall()
        async with conn.cursor(row_factory=class_row(ProbeRunCount)) as cur:
            _ = await cur.execute(
                """
                SELECT user_agent, count(*) AS hits, min(occurred_at) AS first_seen
                FROM telemetry_hits WHERE user_agent LIKE %s
                GROUP BY 1 ORDER BY 3
                """,
                (PROBE_USER_AGENT_PREFIX + "%",),
            )
            probe_runs = await cur.fetchall()

    print("router_group  status   hits  first_seen                 last_seen")
    for g in groups:
        print(
            f"{g.router_group:12}  {g.status_code:6}  {g.hits:5} ",
            f"{g.first_seen:%Y-%m-%d %H:%M:%S%z}  {g.last_seen:%Y-%m-%d %H:%M:%S%z}",
        )
    print(f"\nProbe runs (test data, {PROBE_USER_AGENT_PREFIX}*):")
    for r in probe_runs:
        print(
            f"  {r.user_agent!r:42} {r.hits:5} rows  from {r.first_seen:%Y-%m-%d %H:%M:%S%z}"
        )
    return 0


async def rows(run: str, since: datetime) -> int:
    async with read_only_connection() as conn:
        found = await fetch_run_rows(conn, run, since)
    for r in found:
        print(
            f"{r.id:6} {r.probe or '-'!r:38} {r.ip:15} {r.method!r:8} {r.status_code}",
            f"{r.router_group:9} {r.path[:60]!r}",
        )
    print(f"({len(found)} rows)")
    return 0


class Target(StrEnum):
    """What `verify` sends its requests to."""

    API = "api"
    DECOY = "decoy"


DEFAULT_URLS = {Target.API: DEFAULT_API_URL, Target.DECOY: DEFAULT_DECOY_URL}


def forwarded_for(case: Case, peer_ip: str, as_proxy: bool) -> str | None:
    """The X-Forwarded-For to send, if any. As the decoy app's reverse proxy, send what nginx does:
    the client alone, replacing whatever the client sent. Otherwise a forwarded case sends a chain
    whose first entry is forged, which only a trusted peer's last entry may override."""
    if as_proxy:
        return case.forwarded_client or peer_ip
    if case.forwarded_client:
        return f"{FORGED_IP}, {case.forwarded_client}"
    return None


async def send_all(
    base_url: str, run: str, burst: int, target: Target, as_proxy: bool, peer_ip: str
) -> list[Sent]:
    sent: list[Sent] = []
    counter = 0

    async with httpx.AsyncClient(
        base_url=base_url,
        follow_redirects=False,
        timeout=30,
        headers={USER_AGENT_HEADER: PROBE_USER_AGENT_PREFIX + run},
    ) as client:

        async def send(case: Case) -> Sent:
            nonlocal counter
            counter += 1
            probe = f"{run}-{counter:03d}-{case.label}"
            headers = {PROBE_HEADER: probe, **case.headers}
            forwarded = forwarded_for(case, peer_ip, as_proxy)
            if forwarded:
                headers[FORWARDED_FOR_HEADER] = forwarded
            response = await client.request(
                case.method,
                case.path,
                json=case.json,
                data=case.form,
                content=case.content,
                headers=headers,
            )
            return Sent(
                probe,
                case,
                response.status_code,
                target=response.request.url.raw_path.decode(REQUEST_LINE_ENCODING),
                body_size=len(response.request.content),
            )

        matrix, burst_matrix = (
            (request_matrix(), BURST_CASES)
            if target is Target.API
            else (decoy_request_matrix(), DECOY_BURST_CASES)
        )
        for case in matrix:
            for _ in range(case.repeat):
                sent.append(await send(case))

        burst_cases = [burst_matrix[i % len(burst_matrix)] for i in range(burst)]
        sent.extend(await asyncio.gather(*(send(c) for c in burst_cases)))

    return sent


async def wait_for_rows(run: str, since: datetime, expected: int) -> list[HitRow]:
    """Telemetry is written in the background after each response, so poll until it settles."""
    deadline = time.monotonic() + 15
    found: list[HitRow] = []
    async with read_only_connection() as conn:
        while time.monotonic() < deadline:
            found = await fetch_run_rows(conn, run, since)
            if len(found) >= expected:
                # Give any duplicate writes a moment to land before judging.
                await asyncio.sleep(1)
                return await fetch_run_rows(conn, run, since)
            await asyncio.sleep(0.5)
    return found


def peer_is_trusted(peer_ip: str, forwarded_allow_ips: str) -> bool:
    """Mirror the server's rule: may this peer report the client via X-Forwarded-For?"""
    peer = ipaddress.ip_address(peer_ip)
    for entry in (e.strip() for e in forwarded_allow_ips.split(",")):
        if entry == TRUST_EVERY_PEER:
            return True
        try:
            if peer in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


async def verify(
    base_url: str, run: str, burst: int, peer_ip: str, target: Target, as_proxy: bool
) -> int:
    since = datetime.now(UTC)
    # The peer the API sees: this tool, or the decoy app, which must run on this machine too.
    trusted = peer_is_trusted(peer_ip, get_settings().FORWARDED_ALLOW_IPS)
    print(f"peer {peer_ip} is {'a trusted proxy' if trusted else 'untrusted'}")
    # A forwarded client becomes the origin only if the API trusts the peer that names it, and the
    # decoy app only reads X-Forwarded-For behind its proxy (ADDRESS_HEADER, XFF_DEPTH).
    forwarded_honoured = trusted and (target is Target.API or as_proxy)
    sent = await send_all(base_url, run, burst, target, as_proxy, peer_ip)
    found = await wait_for_rows(run, since, len(sent))

    by_probe: dict[str, list[HitRow]] = {}
    for r in found:
        by_probe.setdefault(r.probe or "", []).append(r)

    failures = 0
    outcomes: Counter[tuple[str, int]] = Counter()
    for s in sent:
        recorded = by_probe.pop(s.probe, [])
        outcomes[(s.case.label, s.status)] += 1
        expected_ip = (
            s.case.forwarded_client
            if s.case.forwarded_client and forwarded_honoured
            else peer_ip
        )
        problem = ""
        if not recorded:
            problem = "MISSING"
        elif len(recorded) > 1:
            problem = f"DUPLICATED x{len(recorded)}"
        elif recorded[0].status_code != s.status:
            problem = f"STATUS db={recorded[0].status_code} client={s.status}"
        elif recorded[0].router_group != s.case.group:
            problem = f"GROUP db={recorded[0].router_group} expected={s.case.group}"
        elif recorded[0].ip != expected_ip:
            problem = f"IP db={recorded[0].ip} expected={expected_ip}"
        elif recorded[0].target != s.target:
            problem = f"TARGET db={recorded[0].target[:60]!r} sent={s.target[:60]!r}"
        elif recorded[0].body_size != (s.body_size if target is Target.DECOY else None):
            # The decoy app reports every body; the API doesn't capture bodies (NULL).
            problem = f"BODY db={recorded[0].body_size} sent={s.body_size}"
        if problem:
            failures += 1
            print(f"FAIL {s.probe:40} {s.case.method} {s.case.path[:60]} -> {problem}")

    for probe, extra in by_probe.items():
        failures += 1
        print(f"FAIL unexpected rows for probe {probe!r}: {[r.id for r in extra]}")

    print("\nOutcomes exercised (label, client status): count")
    for (label, status), count in sorted(outcomes.items()):
        print(f"  {label:20} {status}: {count}")
    print(
        f"\nrun={run} requests={len(sent)} rows={len(found)} failures={failures}",
        f"(inspect with: rows --run {run} --since {since.isoformat()})",
    )
    return 1 if failures else 0


class Command(StrEnum):
    SUMMARY = "summary"
    ROWS = "rows"
    VERIFY = "verify"


class Args(argparse.Namespace):
    """Typed view of the parsed arguments (each attribute is set only by its subcommand)."""

    command: str = ""
    run: str = ""
    since: datetime = EPOCH
    base_url: str = ""
    burst: int = DEFAULT_BURST
    peer_ip: str = DEFAULT_PEER_IP
    target: str = Target.API
    decoy_behind_proxy: bool = False


async def run(args: Args) -> int:
    # The app's pool, opened for this command only; every connection below is borrowed from it.
    async with db_conn_pool:
        match Command(args.command):
            case Command.SUMMARY:
                return await summary()
            case Command.ROWS:
                return await rows(args.run, args.since)
            case Command.VERIFY:
                target = Target(args.target)
                return await verify(
                    args.base_url or DEFAULT_URLS[target],
                    args.run,
                    args.burst,
                    args.peer_ip,
                    target,
                    as_proxy=target is Target.DECOY and args.decoy_behind_proxy,
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _ = sub.add_parser(Command.SUMMARY, help="read-only overview of telemetry_hits")
    rows_parser = sub.add_parser(
        Command.ROWS, help="read-only listing of one probe run"
    )
    _ = rows_parser.add_argument(RUN_OPTION, required=True)
    _ = rows_parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        default=EPOCH,
        help="ISO timestamp lower bound (narrows the scan)",
    )
    verify_parser = sub.add_parser(
        Command.VERIFY, help="send tagged traffic and check the recorded rows"
    )
    _ = verify_parser.add_argument(
        "--target",
        choices=list(Target),
        default=Target.API,
        help="the API itself, or the decoy app, which reports to the API",
    )
    _ = verify_parser.add_argument(
        "--base-url",
        help=f"default: {DEFAULT_API_URL} (api) or {DEFAULT_DECOY_URL} (decoy)",
    )
    _ = verify_parser.add_argument(
        "--decoy-behind-proxy",
        action="store_true",
        help="act as the decoy app's nginx: it was started with ADDRESS_HEADER=x-forwarded-for",
    )
    _ = verify_parser.add_argument(
        RUN_OPTION, default=datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    )
    _ = verify_parser.add_argument(
        "--burst", type=int, default=DEFAULT_BURST, help="concurrent requests"
    )
    _ = verify_parser.add_argument(
        "--peer-ip",
        default=DEFAULT_PEER_IP,
        help="the address the server sees this tool connect from",
    )
    args = parser.parse_args(namespace=Args())

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
