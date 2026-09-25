import asyncio
import random

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from attenborough.db import enums, queries
from attenborough.dependencies import DBConn, RequestOrigin
from attenborough.router import HoneypotRouter

router = HoneypotRouter(prefix="")

_BACKUP_ZIP_PATH = "/backup/db.zip"
_WP_LOGIN_PATH = "/wp-login.php"
_PHPMYADMIN_PATH = "/phpmyadmin/index.php"


@router.get("/.git/config")
async def git_config():
    # Keep scanners engaged with a plausible .git/config
    content = """
[core]
repositoryformatversion = 0
filemode = true
bare = false
"""
    await asyncio.sleep(random.uniform(0.02, 0.2))
    return PlainTextResponse(content, status_code=200)


@router.get("/etc/passwd")
async def etc_passwd():
    fake = "root:x:0:0:root:/root:/bin/bash\nwww-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
    await asyncio.sleep(random.uniform(0.01, 0.15))
    return PlainTextResponse(fake, status_code=200)


@router.get(_WP_LOGIN_PATH)
async def wp_get():
    html = f"<html><body><form method='post' action='{_WP_LOGIN_PATH}'><input name='log'/><input name='pwd'/><button>Login</button></form></body></html>"
    await asyncio.sleep(random.uniform(0.01, 0.2))
    return HTMLResponse(html)


@router.post(_WP_LOGIN_PATH)
async def wp_post(
    request: Request,
    db_conn: DBConn,
    origin: RequestOrigin,
    log: str = "",
    pwd: str = "",
):
    await asyncio.sleep(random.uniform(0.05, 0.5))
    success = random.random() < 0.05
    await queries.create_credential_stuffing_attempt(
        db_conn,
        endpoint_path=str(request.url.path),
        ip_address=str(origin),
        username=log,
        password=pwd,
        was_fake_success=success,
    )
    if success:
        return HTMLResponse("<html><body>Dashboard</body></html>")
    return HTMLResponse(
        "<html><body>ERROR: incorrect username</body></html>", status_code=401
    )


@router.get(_PHPMYADMIN_PATH)
async def phpmyadmin():
    html = f"<html><body><h1>phpMyAdmin</h1><form method='post' action='{_PHPMYADMIN_PATH}'><input name='pma_username' /><input name='pma_password' type='password' /></form></body></html>"
    await asyncio.sleep(random.uniform(0.01, 0.2))
    return HTMLResponse(html)


@router.get(_BACKUP_ZIP_PATH)
async def backup_download(db_conn: DBConn, origin: RequestOrigin):
    # Create a small fake ZIP binary and log a decoy view
    fake_zip = b"PK\x03\x04" + b"FAKEZIPCONTENT"
    # upsert decoy record and log view via generated queries
    decoy_id = await queries.upsert_decoy(
        db_conn,
        type=enums.DecoyType.BINARY,
        slug=router.decoy_slug(_BACKUP_ZIP_PATH),
        added_by_ip=str(origin),
    )
    if decoy_id:
        await queries.create_decoy_view(
            db_conn, decoy_id=decoy_id, ip_address=str(origin)
        )
    await asyncio.sleep(random.uniform(0.05, 0.25))
    return StreamingResponse(
        iter([fake_zip]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=backup.zip"},
    )
