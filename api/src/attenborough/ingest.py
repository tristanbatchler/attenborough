"""Where the decoy app (decoy/) reports its visitors: every request it served, and every login
attempt, whose outcome is decided here. Everything in a report is attacker-controlled: it is bounded
here and recorded as data, never interpreted.

A report names its visitor in X-Forwarded-For, which only counts because the decoy app's address is
in FORWARDED_ALLOW_IPS; the visitor is the `RequestOrigin`.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks
from pydantic import Base64Bytes, BaseModel, Field
from starlette.status import HTTP_204_NO_CONTENT

from attenborough.db import queries
from attenborough.db.enums import RouterGroup
from attenborough.dependencies import DBConn, RequestOrigin
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


class DecoyHit(BaseModel):
    """One request the decoy app served: exactly what the visitor sent, and the status it got."""

    method: str = Field(min_length=1, max_length=_MAX_METHOD_LENGTH)
    # The request line, one character per byte, not decoded or normalised.
    path: str = Field(max_length=_MAX_REQUEST_LINE)
    # After the `?`; None when the request line had none.
    query: str | None = Field(max_length=_MAX_REQUEST_LINE)
    headers: dict[str, str] = Field(max_length=_MAX_HEADERS)
    # Base64 in the JSON report; the whole body, empty when there was none. None when the decoy app
    # couldn't read it (over its BODY_SIZE_LIMIT): not captured, which is not the same as empty.
    body: Annotated[Base64Bytes, Field(max_length=_MAX_BODY_BYTES)] | None
    status_code: int = Field(ge=_MIN_STATUS, le=_MAX_STATUS)


class LoginAttempt(BaseModel):
    """Credentials a visitor submitted to one of the decoy app's login forms."""

    path: str = Field(max_length=_MAX_REQUEST_LINE)
    username: str = Field(max_length=_MAX_BODY_BYTES)
    password: str = Field(max_length=_MAX_BODY_BYTES)


class LoginOutcome(BaseModel):
    """Whether the decoy should treat the login as successful: decided here, not in the decoy app."""

    success: bool


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
    )


@router.post("/logins")
async def report_login(
    attempt: LoginAttempt, db_conn: DBConn, origin: RequestOrigin
) -> LoginOutcome:
    """Record submitted credentials and decide the outcome the decoy app shows."""
    # No decoy account exists yet, so every login fails, as a real site does for guessed
    # credentials. Deterministic on purpose: the same credentials always get the same answer.
    success = False
    await queries.create_credential_stuffing_attempt(
        db_conn,
        endpoint_path=attempt.path,
        ip_address=str(origin),
        username=attempt.username,
        password=attempt.password,
        was_fake_success=success,
    )
    return LoginOutcome(success=success)
