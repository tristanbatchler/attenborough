"""Where the decoy app (decoy/) asks whether to serve a visitor at all, and reports its visitors:
every request it served, and every login attempt and WordPress install, whose outcomes are decided
here. Everything in a report is attacker-controlled: it is bounded
here and recorded as data, never interpreted.

A report names its visitor in X-Forwarded-For, which only counts because the decoy app's address is
in FORWARDED_ALLOW_IPS; the visitor is the `RequestOrigin`.
"""

import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks
from pydantic import Base64Bytes, BaseModel, Field
from starlette.status import HTTP_204_NO_CONTENT

from attenborough import canaries, rules
from attenborough.db import queries
from attenborough.db.enums import RouterGroup
from attenborough.dependencies import DBConn, RequestOrigin
from attenborough.rules import RenderedResponse, Request
from attenborough.telemetry import record_hit

router = APIRouter(prefix="/ingest", tags=[RouterGroup.INGEST])

# The limits match what the decoy app's Node server accepts, so a report is never rejected for
# describing a request the server really served. Node caps the request line and headers together
# at 16 KiB (--max-http-header-size) and the header count at 2000 (maxHeadersCount).
_MAX_REQUEST_LINE = 16 * 1024
_MAX_HEADERS = 2000
# Bodies arrive whole, up to the decoy app's BODY_SIZE_LIMIT (1M in decoy/.env.example, nginx's
# default client_max_body_size, so nothing bigger reaches it in production). record_hit decides how
# much is stored. Also bounds submitted credentials, parsed from one.
_MAX_BODY_BYTES = 1024 * 1024
# Longer than any real HTTP method; Node's parser only accepts registered ones anyway.
_MAX_METHOD_LENGTH = 32
_MIN_STATUS = 100
_MAX_STATUS = 599

# The tarpit, for fast guessers: an address's first TARPIT_FREE_ATTEMPTS logins in TARPIT_WINDOW are
# answered at once; after that each waits TARPIT_STEP_MS longer than the last, up to
# TARPIT_MAX_DELAY_MS (under nginx's 60 s proxy timeout, so the visitor still gets the page). It
# slows a guesser down without ever blocking one, and forgets an address that slows down itself.
TARPIT_WINDOW = timedelta(minutes=10)
TARPIT_FREE_ATTEMPTS = 10
TARPIT_STEP_MS = 500
TARPIT_MAX_DELAY_MS = 15_000
# The password WordPress's installer makes up when none is chosen: wp_generate_password(12, false),
# letters and digits.
_GENERATED_PASSWORD_LENGTH = 12
_GENERATED_PASSWORD_ALPHABET = string.ascii_letters + string.digits
# What PHP's trim() strips, which is what WordPress stores of a chosen password.
_PHP_WHITESPACE = " \t\n\r\0\x0b"


def tarpit_delay_ms(previous_attempts: int) -> int:
    """How long to make an address wait, given how many logins it tried in the last
    TARPIT_WINDOW."""
    excess = max(0, previous_attempts - TARPIT_FREE_ATTEMPTS + 1)
    return min(excess * TARPIT_STEP_MS, TARPIT_MAX_DELAY_MS)


class Visit(BaseModel):
    """A request the decoy app received, as the visitor sent it."""

    method: str = Field(min_length=1, max_length=_MAX_METHOD_LENGTH)
    # The request line, one character per byte, not decoded or normalised.
    path: str = Field(max_length=_MAX_REQUEST_LINE)
    # After the `?`; None when the request line had none.
    query: str | None = Field(max_length=_MAX_REQUEST_LINE)
    headers: dict[str, str] = Field(max_length=_MAX_HEADERS)


class DecoyHit(Visit):
    """One request the decoy app served: exactly what the visitor sent, and the status it got."""

    # Base64 in the JSON report; the whole body, empty when there was none. None when the decoy app
    # couldn't read it (over its BODY_SIZE_LIMIT): not captured, which is not the same as empty.
    body: Annotated[Base64Bytes, Field(max_length=_MAX_BODY_BYTES)] | None
    status_code: int = Field(ge=_MIN_STATUS, le=_MAX_STATUS)
    # Whether the decoy refused the request because the address is banned (judge_visit).
    banned: bool
    # The response rule that answered it instead of the decoy's own page (judge_visit), if any.
    rule_id: int | None


class VisitVerdict(BaseModel):
    """How the decoy should answer a request."""

    # Banned (admin.py): the decoy refuses it, and still reports the request.
    banned: bool
    # A response rule's answer (rules.py), served instead of the decoy's own page, and the rule's
    # id, reported with the hit; both null for the decoy's own page, and when banned.
    rule_id: int | None
    response: RenderedResponse | None


class LoginAttempt(BaseModel):
    """Credentials a visitor submitted to one of the decoy app's login forms."""

    path: str = Field(max_length=_MAX_REQUEST_LINE)
    username: str = Field(max_length=_MAX_BODY_BYTES)
    password: str = Field(max_length=_MAX_BODY_BYTES)


class LoginOutcome(BaseModel):
    """How the decoy should answer a login: decided here, not in the decoy app."""

    # The decoy pretends to accept a login only into an account an install created, with its
    # password: nothing is ever really logged in.
    success: bool
    # Whether the login named an account an install created, whatever the password: WordPress says
    # such an account's password was wrong, rather than that it isn't registered.
    known_account: bool
    # How long to wait before answering: the tarpit for persistent guessers (tarpit_delay_ms).
    delay_ms: int = Field(ge=0, le=TARPIT_MAX_DELAY_MS)


class InstallAttempt(BaseModel):
    """A WordPress install the decoy app's installer accepted: the site and administrator account
    the visitor chose, as submitted. The installer has already checked them as WordPress does."""

    path: str = Field(max_length=_MAX_REQUEST_LINE)
    site_title: str = Field(max_length=_MAX_BODY_BYTES)
    username: str = Field(max_length=_MAX_BODY_BYTES)
    email: str = Field(max_length=_MAX_BODY_BYTES)
    password: str = Field(max_length=_MAX_BODY_BYTES)


class InstallOutcome(BaseModel):
    """The installed account's password, when WordPress made one up (none was chosen): the
    installer shows it. Null when the visitor chose their own."""

    generated_password: str | None


class CanaryRequest(BaseModel):
    """A leaked file the decoy is about to serve."""

    path: str = Field(max_length=_MAX_REQUEST_LINE)


class Canary(BaseModel):
    """The secret to put in it: fresh, random, and recorded against the visitor."""

    secret: str


@router.post("/visits")
async def judge_visit(
    visit: Visit, db_conn: DBConn, origin: RequestOrigin
) -> VisitVerdict:
    """Asked before the decoy serves each request: is the visitor banned, and if not, does a
    response rule answer instead (rules.respond)? Never cached, so a change to a ban or a rule
    applies to the very next request."""
    address = str(origin)
    if await queries.is_ip_banned(db_conn, ip_address=address):
        return VisitVerdict(banned=True, rule_id=None, response=None)
    request = Request(
        method=visit.method, path=visit.path, query=visit.query, headers=visit.headers
    )
    answer = await rules.respond(db_conn, address, request)
    if answer is None:
        return VisitVerdict(banned=False, rule_id=None, response=None)
    rule_id, response = answer
    return VisitVerdict(banned=False, rule_id=rule_id, response=response)


@router.post("/hits", status_code=HTTP_204_NO_CONTENT)
async def report_hit(
    hit: DecoyHit, origin: RequestOrigin, background_tasks: BackgroundTasks
) -> None:
    """Record a request the decoy app served, as a honeypot hit.

    Written after this response, so the decoy app waits only for the round trip, not the database.
    """
    background_tasks.add_task(
        record_hit,
        ip_address=str(origin),
        method=hit.method,
        path=hit.path,
        query=hit.query,
        router_group=RouterGroup.HONEYPOT,
        headers=hit.headers,
        body=hit.body,
        status_code=hit.status_code,
        banned=hit.banned,
        rule_id=hit.rule_id,
    )


@router.post("/logins")
async def report_login(
    attempt: LoginAttempt, db_conn: DBConn, origin: RequestOrigin
) -> LoginOutcome:
    """Record submitted credentials and decide the outcome the decoy app shows.

    The only accounts are the ones installs created (report_install), so only those open, with
    their own password. Every other login fails, as a real site does for guessed credentials,
    canaries included: they were never anyone's password. The attempt is linked to the canary or
    install it used (CreateCredentialStuffingAttempt).
    """
    previous = await queries.count_login_attempts_since(
        db_conn, ip_address=str(origin), since=datetime.now(UTC) - TARPIT_WINDOW
    )
    recorded = await queries.create_credential_stuffing_attempt(
        db_conn,
        endpoint_path=attempt.path,
        ip_address=str(origin),
        username=attempt.username,
        password=attempt.password,
    )
    if recorded is None:
        # Unreachable: INSERT ... RETURNING returns the row it inserted.
        raise RuntimeError("Recording a login attempt returned no row")
    return LoginOutcome(
        success=recorded.was_fake_success,
        known_account=recorded.known_account,
        delay_ms=tarpit_delay_ms(previous or 0),
    )


def account_password(chosen: str) -> tuple[str, bool]:
    """An installed account's password, as wp_install() decides it, and whether it was made up:
    the chosen one, trimmed, or a random one (wp_generate_password(12, false)) if that leaves
    nothing."""
    trimmed = chosen.strip(_PHP_WHITESPACE)
    if trimmed:
        return trimmed, False
    generated = "".join(
        secrets.choice(_GENERATED_PASSWORD_ALPHABET)
        for _ in range(_GENERATED_PASSWORD_LENGTH)
    )
    return generated, True


@router.post("/installs")
async def report_install(
    install: InstallAttempt, db_conn: DBConn, origin: RequestOrigin
) -> InstallOutcome:
    """Record a WordPress install and decide its account's password (account_password).
    Nothing is installed; a later login with the account is linked to this install."""
    password, generated = account_password(install.password)
    _ = await queries.create_install_attempt(
        db_conn,
        ip_address=str(origin),
        path=install.path,
        site_title=install.site_title,
        username=install.username,
        email=install.email,
        password=password,
        password_generated=generated,
    )
    return InstallOutcome(generated_password=password if generated else None)


@router.post("/canaries")
async def issue_canary(
    leak: CanaryRequest, db_conn: DBConn, origin: RequestOrigin
) -> Canary:
    """A fresh secret for a leaked file the decoy is serving, recorded against the visitor."""
    return Canary(
        secret=await canaries.issue_canary(
            db_conn, path=leak.path, ip_address=str(origin)
        )
    )
