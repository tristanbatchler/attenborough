"""The admin login: Google's OAuth authorization code flow with PKCE, for ADMIN_EMAILS only, and the
sessions it starts. The exhibit's web server is the only caller: it sends the admin to Google, hands
the callback's code here, keeps the session token in its own cookie, and sends it back as a bearer
token on every admin call. Nobody else gets a session, or learns that one could exist: every
refusal is a 404, like an unknown path.
"""

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import AsyncConnection
from pydantic import BaseModel, Field

from attenborough import settings
from attenborough.db import queries
from attenborough.db.enums import AuditAction, RouterGroup
from attenborough.dependencies import DBConn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=[RouterGroup.ADMIN])

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_HOST = "oauth2.googleapis.com"
_GOOGLE_TOKEN_PATH = "/token"
# What an ID token's `iss` may be (Google's OpenID Connect documentation).
_GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
_SCOPES = "openid email profile"
# The web app's route Google redirects to.
_CALLBACK_PATH = "/auth/google/callback"
_GOOGLE_TIMEOUT_SECONDS = 10
# How long the admin has to come back from Google's consent screen.
_STATE_LIFETIME = timedelta(minutes=10)
# Random bytes in a state and a session token; a PKCE verifier must be 43 to 128 characters.
_TOKEN_BYTES = 32
_VERIFIER_BYTES = 64
# The bounds of what the web app passes on from Google's redirect.
_MAX_CODE_LENGTH = 2048
_MAX_STATE_LENGTH = 128
# A JWT: header, payload and signature, base64url-encoded and joined by dots.
_JWT_SEPARATOR = "."
_JWT_PARTS = 3
_BASE64_BLOCK = 4
_BASE64_PADDING = "="
# The authorization code: its parameter's name, and the response_type that asks for one.
_CODE = "code"


class GoogleLogin(BaseModel):
    """Where to send the admin to log in."""

    url: str


class GoogleCallback(BaseModel):
    """What Google's redirect to the web app carried."""

    code: str = Field(min_length=1, max_length=_MAX_CODE_LENGTH)
    state: str = Field(min_length=1, max_length=_MAX_STATE_LENGTH)


class Session(BaseModel):
    """A new session: the token to send as a bearer token, and when it stops working."""

    token: str
    expires_at: datetime


class Me(BaseModel):
    """Who is logged in."""

    email: str
    name: str


class _TokenResponse(BaseModel):
    id_token: str


class _IdTokenClaims(BaseModel):
    """The ID token's claims this login relies on."""

    iss: str
    aud: str
    exp: int
    sub: str
    email: str
    email_verified: bool
    name: str


@dataclass(frozen=True)
class AdminSession:
    """The admin a request's session belongs to."""

    user_id: int
    email: str
    name: str
    token_hash: str


def _not_found() -> HTTPException:
    return HTTPException(HTTPStatus.NOT_FOUND)


def _hash_token(token: str) -> str:
    """Sessions are stored only as the SHA-256 of their token."""
    return hashlib.sha256(token.encode()).hexdigest()


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip(_BASE64_PADDING)


def _jwt_payload(token: str) -> bytes:
    parts = token.split(_JWT_SEPARATOR)
    if len(parts) != _JWT_PARTS:
        raise ValueError("Google's ID token is not a JWT")
    payload = parts[1]
    padding = _BASE64_PADDING * (-len(payload) % _BASE64_BLOCK)
    return base64.urlsafe_b64decode(payload + padding)


def _client() -> dict[str, str]:
    """Who is asking Google, and where it sends the admin back: in both of the flow's requests."""
    return {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.WEB_BASE_URL + _CALLBACK_PATH,
    }


def is_admin_email(email: str) -> bool:
    return email.lower() in settings.ADMIN_EMAILS


async def _google_identity(code: str, code_verifier: str) -> _IdTokenClaims:
    """Exchange the code for Google's ID token, and read who logged in from it.

    The token comes straight from Google's token endpoint over TLS, in answer to our client
    secret, so its signature needs no checking (Google's OpenID Connect documentation, "Obtain
    user information from the ID token"); its issuer, audience and expiry still are. In a
    deployment, the request goes through nginx (GOOGLE_TOKEN_SOCKET), which makes the TLS
    connection to Google and verifies its certificate.
    """
    if settings.GOOGLE_TOKEN_SOCKET is None:
        transport, scheme = None, "https"
    else:
        transport = httpx.AsyncHTTPTransport(uds=str(settings.GOOGLE_TOKEN_SOCKET))
        scheme = "http"
    async with httpx.AsyncClient(
        transport=transport, timeout=_GOOGLE_TIMEOUT_SECONDS
    ) as client:
        response = await client.post(
            f"{scheme}://{_GOOGLE_TOKEN_HOST}{_GOOGLE_TOKEN_PATH}",
            data={
                **_client(),
                "grant_type": "authorization_code",
                _CODE: code,
                "code_verifier": code_verifier,
                "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
            },
        )
    if response.status_code != HTTPStatus.OK:
        # A code that was forged, replayed or expired; Google's reason isn't ours to pass on.
        logger.warning("Google refused a login's code (%d)", response.status_code)
        raise _not_found()
    id_token = _TokenResponse.model_validate_json(response.content).id_token
    claims = _IdTokenClaims.model_validate_json(_jwt_payload(id_token))
    if (
        claims.iss not in _GOOGLE_ISSUERS
        or claims.aud != settings.GOOGLE_CLIENT_ID
        or claims.exp <= datetime.now(UTC).timestamp()
    ):
        raise ValueError("Google's ID token is not for this client, or has expired")
    return claims


async def audit(
    db_conn: AsyncConnection,
    admin: AdminSession,
    action: AuditAction,
    target_ip: str | None = None,
    details: dict[str, str | None] | None = None,
) -> None:
    """Record an admin action in the audit log."""
    await queries.create_audit_log_entry(
        db_conn,
        user_id=admin.user_id,
        action=action,
        target_ip=target_ip,
        details=json.dumps(details or {}),
    )


_bearer = HTTPBearer(auto_error=False)


async def current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db_conn: DBConn,
) -> AdminSession:
    """The admin whose session the request carries, or a 404 for anyone else."""
    if credentials is None:
        raise _not_found()
    token_hash = _hash_token(credentials.credentials)
    user = await queries.use_session(db_conn, token_hash=token_hash)
    if user is None or not is_admin_email(user.email):
        raise _not_found()
    return AdminSession(
        user_id=user.id_, email=user.email, name=user.name, token_hash=token_hash
    )


CurrentAdmin = Annotated[AdminSession, Depends(current_admin)]


@router.get("/google")
async def start_google_login(db_conn: DBConn) -> GoogleLogin:
    """Where to send the admin: Google's consent screen, with a fresh state and PKCE challenge."""
    state = secrets.token_urlsafe(_TOKEN_BYTES)
    code_verifier = secrets.token_urlsafe(_VERIFIER_BYTES)
    await queries.prune_o_auth_states(db_conn)
    await queries.create_o_auth_state(
        db_conn,
        state=state,
        code_verifier=code_verifier,
        expires=datetime.now(UTC) + _STATE_LIFETIME,
    )
    query = urlencode(
        {
            **_client(),
            "response_type": _CODE,
            "scope": _SCOPES,
            "state": state,
            "code_challenge": _base64url(
                hashlib.sha256(code_verifier.encode()).digest()
            ),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return GoogleLogin(url=f"{_GOOGLE_AUTHORIZE_URL}?{query}")


@router.post("/google/callback")
async def finish_google_login(callback: GoogleCallback, db_conn: DBConn) -> Session:
    """Finish a login: a session for a verified ADMIN_EMAILS account, a 404 for anything else.
    The state is used up whatever happens, so the same callback never works twice."""
    code_verifier = await queries.take_o_auth_state(db_conn, state=callback.state)
    if code_verifier is None:
        raise _not_found()
    try:
        identity = await _google_identity(callback.code, code_verifier)
    except httpx.HTTPError as exc:
        logger.error("Could not reach Google's token endpoint: %r", exc)
        raise HTTPException(HTTPStatus.BAD_GATEWAY) from exc
    if not identity.email_verified or not is_admin_email(identity.email):
        logger.warning("Refused a Google login: not an admin")
        raise _not_found()

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = datetime.now(UTC) + timedelta(days=settings.SESSION_DURATION_DAYS)
    async with db_conn.transaction():
        await queries.prune_sessions(db_conn)
        user_id = await queries.upsert_user(
            db_conn, google_sub=identity.sub, email=identity.email, name=identity.name
        )
        if user_id is None:
            # Unreachable: INSERT ... ON CONFLICT DO UPDATE ... RETURNING returns the row.
            raise RuntimeError("Upserting a user returned no row")
        token_hash = _hash_token(token)
        await queries.create_session(
            db_conn, user_id=user_id, token_hash=token_hash, expires=expires_at
        )
        admin = AdminSession(
            user_id=user_id,
            email=identity.email,
            name=identity.name,
            token_hash=token_hash,
        )
        await audit(db_conn, admin, AuditAction.LOGIN)
    return Session(token=token, expires_at=expires_at)


@router.get("/me")
async def get_me(admin: CurrentAdmin) -> Me:
    return Me(email=admin.email, name=admin.name)


@router.post("/logout", status_code=HTTPStatus.NO_CONTENT)
async def log_out(admin: CurrentAdmin, db_conn: DBConn) -> None:
    """End this session."""
    await queries.delete_session(db_conn, token_hash=admin.token_hash)
