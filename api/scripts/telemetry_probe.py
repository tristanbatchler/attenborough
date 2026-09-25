"""Test and troubleshoot Attenborough request telemetry against a running server and its database.

Run from `api/` with the project environment, e.g. `uv run python scripts/telemetry_probe.py summary`.
Database settings come from the application's own `Settings` (`api/.env` plus environment overrides).

Subcommands:
  summary               Read-only overview of `telemetry_hits`: counts per group/status and probe rows.
  rows --run TAG        Read-only listing of the rows recorded for one probe run.
  verify --base-url URL Send a tagged request matrix (plus a concurrent burst) to a running server, then
                        check that every request produced exactly one row with the status the client
                        received and the expected router group. Exits 1 on any mismatch.

Every probe request carries `User-Agent: attenborough-probe/<run>` and a unique `x-probe: <run>-<n>-<label>`
header, so rows map one-to-one onto requests and test data can be identified later. `verify` writes real
rows (telemetry, credential attempts, decoy events) to the configured database; the inspection commands
only read.
"""

import argparse
import asyncio
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPMethod

import httpx
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import class_row

from attenborough.router.group import RouterGroup
from attenborough.settings import get_settings

PROBE_USER_AGENT_PREFIX = "attenborough-probe/"
PROBE_HEADER = "x-probe"
PROBE_CREDENTIAL = "probe"
CREDENTIALS = {"username": PROBE_CREDENTIAL, "password": PROBE_CREDENTIAL}
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_BURST = 100
RUN_OPTION = "--run"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
AUTH_LOGIN_PATH = "/auth/login"
PROTECTED_SECRET_PATH = "/protected/secret"
NESTED_EXHIBIT_PATH = "/exhibit/feed/test"
ADMIN_DASHBOARD_PATH = "/admin/dashboard"


@dataclass(frozen=True)
class Case:
    label: str
    method: HTTPMethod
    path: str
    group: RouterGroup
    json: object = None
    headers: dict[str, str] = field(default_factory=dict[str, str])
    repeat: int = 1


def request_matrix(real_ip_header: str) -> list[Case]:
    """One case per outcome the telemetry must record identically: OK, redirect, returned and raised
    errors, framework errors (404/405/422), unhandled exceptions, and framework routes."""
    return [
        Case("root", HTTPMethod.GET, "/", RouterGroup.SYSTEM),
        Case("html", HTTPMethod.GET, ADMIN_DASHBOARD_PATH, RouterGroup.HONEYPOT),
        Case("router-test", HTTPMethod.GET, "/admin/test", RouterGroup.HONEYPOT),
        Case(
            "nested-exhibit", HTTPMethod.GET, NESTED_EXHIBIT_PATH, RouterGroup.EXHIBIT
        ),
        Case(
            "exhibit-ip",
            HTTPMethod.GET,
            "/exhibit/ip/127.0.0.1/activity?take=1",
            RouterGroup.EXHIBIT,
        ),
        Case("gitconfig", HTTPMethod.GET, "/.git/config", RouterGroup.HONEYPOT),
        Case("wp-get", HTTPMethod.GET, "/wp-login.php", RouterGroup.HONEYPOT),
        Case("zip-decoy", HTTPMethod.GET, "/backup/db.zip", RouterGroup.HONEYPOT),
        Case(
            "401-returned", HTTPMethod.GET, PROTECTED_SECRET_PATH, RouterGroup.HONEYPOT
        ),
        Case(
            "401-returned-post",
            HTTPMethod.POST,
            "/protected/secret/unlock",
            RouterGroup.HONEYPOT,
            json="wrong",
        ),
        Case(
            "wp-post",
            HTTPMethod.POST,
            f"/wp-login.php?log={PROBE_CREDENTIAL}&pwd={PROBE_CREDENTIAL}",
            RouterGroup.HONEYPOT,
        ),
        # Randomised decoys: repeated so both the success (303) and raised-error branches are hit.
        Case(
            "auth-login",
            HTTPMethod.POST,
            AUTH_LOGIN_PATH,
            RouterGroup.HONEYPOT,
            json=CREDENTIALS,
            repeat=10,
        ),
        Case(
            "admin-login",
            HTTPMethod.POST,
            "/admin/login",
            RouterGroup.HONEYPOT,
            json=CREDENTIALS,
            repeat=10,
        ),
        Case("404", HTTPMethod.GET, "/this/does/not/exist", RouterGroup.HONEYPOT),
        Case("405", HTTPMethod.DELETE, ADMIN_DASHBOARD_PATH, RouterGroup.HONEYPOT),
        Case("422", HTTPMethod.POST, AUTH_LOGIN_PATH, RouterGroup.HONEYPOT, json={}),
        Case(
            "bad-real-ip",
            HTTPMethod.GET,
            ADMIN_DASHBOARD_PATH,
            RouterGroup.HONEYPOT,
            headers={real_ip_header: "not-an-ip"},
        ),
        Case("docs", HTTPMethod.GET, "/docs", RouterGroup.SYSTEM),
        Case("openapi", HTTPMethod.GET, "/openapi.json", RouterGroup.SYSTEM),
        # Currently an unhandled exception (invalid inet cast). If input validation is added this
        # stops exercising the unhandled-500 path; replace it with another unhandled failure.
        Case(
            "unhandled-500",
            HTTPMethod.GET,
            "/exhibit/ip/not-an-ip/activity",
            RouterGroup.EXHIBIT,
        ),
    ]


BURST_CASES = [
    Case("burst-ok", HTTPMethod.GET, ADMIN_DASHBOARD_PATH, RouterGroup.HONEYPOT),
    Case("burst-404", HTTPMethod.GET, "/burst/not/found", RouterGroup.HONEYPOT),
    Case("burst-401", HTTPMethod.GET, PROTECTED_SECRET_PATH, RouterGroup.HONEYPOT),
    Case("burst-nested", HTTPMethod.GET, NESTED_EXHIBIT_PATH, RouterGroup.EXHIBIT),
]


@dataclass(frozen=True)
class Sent:
    probe: str
    case: Case
    status: int


@dataclass(frozen=True)
class HitRow:
    id: int
    probe: str | None
    ip: str
    method: str
    path: str
    router_group: str
    status_code: int
    occurred_at: datetime


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


async def connect() -> AsyncConnection:
    settings = get_settings()
    conninfo = make_conninfo(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USERNAME,
        password=settings.DB_PASSWORD,
        dbname=settings.DB_DATABASE,
    )
    conn = await AsyncConnection.connect(conninfo, autocommit=True)
    # This tool only ever inspects; the server under test does all writing.
    _ = await conn.execute("SET default_transaction_read_only = on")
    return conn


async def fetch_run_rows(
    conn: AsyncConnection, run: str, since: datetime
) -> list[HitRow]:
    async with conn.cursor(row_factory=class_row(HitRow)) as cur:
        _ = await cur.execute(
            """
            SELECT id, headers->>%s AS probe, host(ip_address) AS ip, method, path,
                   router_group, status_code, occurred_at
            FROM telemetry_hits
            WHERE occurred_at >= %s AND user_agent = %s
            ORDER BY id
            """,
            (PROBE_HEADER, since, PROBE_USER_AGENT_PREFIX + run),
        )
        return await cur.fetchall()


async def summary() -> int:
    async with await connect() as conn:
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
            f"  {r.user_agent:40} {r.hits:5} rows  from {r.first_seen:%Y-%m-%d %H:%M:%S%z}"
        )
    return 0


async def rows(run: str, since: datetime) -> int:
    async with await connect() as conn:
        found = await fetch_run_rows(conn, run, since)
    for r in found:
        print(
            f"{r.id:6} {r.probe or '-':36} {r.ip:15} {r.method:6} {r.status_code}",
            f"{r.router_group:9} {r.path[:60]!r}",
        )
    print(f"({len(found)} rows)")
    return 0


async def send_all(base_url: str, run: str, burst: int) -> list[Sent]:
    settings = get_settings()
    sent: list[Sent] = []
    counter = 0

    async with httpx.AsyncClient(
        base_url=base_url,
        follow_redirects=False,
        timeout=30,
        headers={"user-agent": PROBE_USER_AGENT_PREFIX + run},
    ) as client:

        async def send(case: Case) -> Sent:
            nonlocal counter
            counter += 1
            probe = f"{run}-{counter:03d}-{case.label}"
            response = await client.request(
                case.method,
                case.path,
                json=case.json,
                headers={PROBE_HEADER: probe, **case.headers},
            )
            return Sent(probe, case, response.status_code)

        for case in request_matrix(settings.REAL_IP_HEADER):
            for _ in range(case.repeat):
                sent.append(await send(case))

        burst_cases = [BURST_CASES[i % len(BURST_CASES)] for i in range(burst)]
        sent.extend(await asyncio.gather(*(send(c) for c in burst_cases)))

    return sent


async def wait_for_rows(run: str, since: datetime, expected: int) -> list[HitRow]:
    """Telemetry is written in the background after each response, so poll until it settles."""
    deadline = time.monotonic() + 15
    found: list[HitRow] = []
    async with await connect() as conn:
        while time.monotonic() < deadline:
            found = await fetch_run_rows(conn, run, since)
            if len(found) >= expected:
                # Give any duplicate writes a moment to land before judging.
                await asyncio.sleep(1)
                return await fetch_run_rows(conn, run, since)
            await asyncio.sleep(0.5)
    return found


async def verify(base_url: str, run: str, burst: int) -> int:
    since = datetime.now(UTC)
    sent = await send_all(base_url, run, burst)
    found = await wait_for_rows(run, since, len(sent))

    by_probe: dict[str, list[HitRow]] = {}
    for r in found:
        by_probe.setdefault(r.probe or "", []).append(r)

    failures = 0
    outcomes: Counter[tuple[str, int]] = Counter()
    for s in sent:
        recorded = by_probe.pop(s.probe, [])
        outcomes[(s.case.label, s.status)] += 1
        problem = ""
        if not recorded:
            problem = "MISSING"
        elif len(recorded) > 1:
            problem = f"DUPLICATED x{len(recorded)}"
        elif recorded[0].status_code != s.status:
            problem = f"STATUS db={recorded[0].status_code} client={s.status}"
        elif recorded[0].router_group != s.case.group:
            problem = f"GROUP db={recorded[0].router_group} expected={s.case.group}"
        if problem:
            failures += 1
            print(f"FAIL {s.probe:40} {s.case.method} {s.case.path} -> {problem}")

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
    base_url: str = DEFAULT_BASE_URL
    burst: int = DEFAULT_BURST


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
    _ = verify_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    _ = verify_parser.add_argument(
        RUN_OPTION, default=datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    )
    _ = verify_parser.add_argument(
        "--burst", type=int, default=DEFAULT_BURST, help="concurrent requests"
    )
    args = parser.parse_args(namespace=Args())

    match Command(args.command):
        case Command.SUMMARY:
            return asyncio.run(summary())
        case Command.ROWS:
            return asyncio.run(rows(args.run, args.since))
        case Command.VERIFY:
            return asyncio.run(verify(args.base_url, args.run, args.burst))


if __name__ == "__main__":
    sys.exit(main())
