import asyncio
import random
from typing import Annotated

from fastapi import Body, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.status import HTTP_303_SEE_OTHER, HTTP_401_UNAUTHORIZED

from attenborough.db import queries
from attenborough.dependencies import DBConn, RequestOrigin
from attenborough.router import HoneypotRouter

router = HoneypotRouter(prefix="/auth")

_LOGIN_PATH = "/login"


@router.get(_LOGIN_PATH)
async def get_login():
    # Present a fake login page to keep scanners engaged
    html = f"""
	<html><head><title>Login</title></head>
	<body>
	<form method="post" action="{router.prefix}{_LOGIN_PATH}">
	  <input name="username" />
	  <input name="password" type="password" />
	  <button type="submit">Log in</button>
	</form>
	</body></html>
	"""
    return HTMLResponse(html)


@router.post(_LOGIN_PATH)
async def post_login(
    request: Request,
    username: Annotated[str, Body()],
    password: Annotated[str, Body()],
    db_conn: DBConn,
    origin: RequestOrigin,
):
    # Small random delay to appear realistic
    await asyncio.sleep(random.uniform(0.05, 0.4))

    success = random.random() < 0.1
    router.logger.info(
        "Auth login attempt %s from %s (success=%s)", username, origin, success
    )

    async with db_conn.transaction():
        await queries.create_credential_stuffing_attempt(
            db_conn,
            endpoint_path=str(request.url.path),
            ip_address=str(origin),
            username=username,
            password=password,
            was_fake_success=success,
        )

    if success:
        return HTMLResponse(
            "<html><body>Welcome</body></html>", status_code=HTTP_303_SEE_OTHER
        )

    raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid credentials")
