import random
from typing import Annotated

from fastapi import Body, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER, HTTP_500_INTERNAL_SERVER_ERROR

from attenborough.db import queries
from attenborough.dependencies import DBConn, RequestOrigin
from attenborough.router import Router

router = Router(prefix="/admin")


@router.get("/dashboard")
async def dashboard():
    router.logger.info("Dashboard accessed")
    return HTMLResponse("<html><body>Dashboard</body></html>")


@router.post("/login")
async def login(
    request: Request, username: Annotated[str, Body()], password: Annotated[str, Body()], db_conn: DBConn, origin: RequestOrigin
):
    router.logger.info(f"Login attempt: {username=}, password_length={password}")

    if random.random() < 0.5:
        return RedirectResponse(
            router.url_for(request, dashboard), status_code=HTTP_303_SEE_OTHER
        )

    async with db_conn.transaction():
        await queries.create_credential_stuffing_attempt(db_conn, endpoint_path=request.url.path, ip_address=str(origin), username=username, password=password)

    raise HTTPException(
        HTTP_500_INTERNAL_SERVER_ERROR, "Incorrect username or password"
    )
