import asyncio
import random
from typing import Annotated

from fastapi import Body
from fastapi.responses import PlainTextResponse
from starlette.status import HTTP_401_UNAUTHORIZED

from attenborough.db import enums, queries
from attenborough.dependencies import DBConn, RequestOrigin
from attenborough.router import HoneypotRouter

router = HoneypotRouter(prefix="/protected")

_DECOY_PASSWORD = "letmein"
_SECRET_PATH = "/secret"


@router.get(_SECRET_PATH)
async def secret_get():
    # Challenge with Basic-like header to attract scanners
    return PlainTextResponse(
        "Unauthorized",
        status_code=HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": 'Basic realm="Restricted"'},
    )


@router.post(f"{_SECRET_PATH}/unlock")
async def secret_unlock(
    password: Annotated[str, Body()],
    db_conn: DBConn,
    origin: RequestOrigin,
):
    await asyncio.sleep(random.uniform(0.05, 0.4))
    # simple check against a weak decoy password to let some attempts 'succeed'
    success = password == _DECOY_PASSWORD

    # ensure decoy exists and log password attempt via generated queries
    decoy_id = await queries.upsert_decoy(
        db_conn,
        type=enums.DecoyType.TEXT,
        slug=router.decoy_slug(_SECRET_PATH),
        added_by_ip=str(origin),
    )
    if decoy_id:
        await queries.create_decoy_password_attempt(
            db_conn, decoy_id=decoy_id, ip_address=str(origin), successful=success
        )

    if success:
        return PlainTextResponse("SECRET: the-api-key-IS-FAKE-1234\n", status_code=200)

    return PlainTextResponse("Forbidden", status_code=HTTP_401_UNAUTHORIZED)
