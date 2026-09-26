"""What the decoy app (decoy/) reports about its visitors. Everything in these models is
attacker-controlled: it is bounded here and recorded as data, never interpreted."""

from typing import Annotated

from pydantic import Base64Bytes, BaseModel, Field

# The limits match what the decoy app's Node server accepts, so a report is never rejected for
# describing a request the server really served. Node caps the request line and headers together
# at 16 KiB (--max-http-header-size) and the header count at 2000 (maxHeadersCount).
_MAX_REQUEST_LINE = 16 * 1024
_MAX_HEADERS = 2000
# Bodies arrive whole, up to the decoy app's BODY_SIZE_LIMIT (1M in decoy/.env.example, nginx's
# default client_max_body_size, so nothing bigger reaches it in production). telemetry.py decides how much is stored. Also bounds submitted credentials, parsed from one.
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
