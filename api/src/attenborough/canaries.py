"""Canaries: fresh random secrets the decoy hands out (its leaked files, and response rules that use
`{{ canary }}`), each recorded against the visitor it was given to. They open nothing; a login that
uses one is linked to it (queries.sql, CreateCredentialStuffingAttempt).
"""

import secrets

from psycopg import AsyncConnection

from attenborough.db import queries

# Random bytes in a canary secret: 24 URL-safe characters, an ordinary-looking strong password.
_CANARY_BYTES = 18


async def issue_canary(conn: AsyncConnection, *, path: str, ip_address: str) -> str:
    """A fresh secret, recorded as handed to `ip_address` at `path`."""
    secret = secrets.token_urlsafe(_CANARY_BYTES)
    await queries.create_canary_token(
        conn, token=secret, path=path, ip_address=ip_address
    )
    return secret
