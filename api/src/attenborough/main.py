import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from attenborough import settings
from attenborough.db import ops
from attenborough.db.schema import SchemaStatus, reset_schema, schema_status
from attenborough.exhibit.routers import exported_routers as exhibit_routers
from attenborough.honeypot.routers import exported_routers as honeypot_routers
from attenborough.middleware import TelemetryMiddleware
from attenborough.response_models import Message
from attenborough.router import ExhibitRouter, Router
from attenborough.settings import write_example_env
from attenborough.util import ROOT_LOGGER_NAME

logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)

logger = logging.getLogger(name=ROOT_LOGGER_NAME)

_TERMINAL = Path("/dev/tty")
_YES_ANSWERS = frozenset({"y", "yes"})


def _confirm_on_terminal(question: str) -> bool:
    """Ask on the controlling terminal. Without one (Docker, systemd, CI) the answer is no.

    /dev/tty rather than stdin: under `uvicorn --reload` the app runs in a child process whose
    stdin is not the keyboard, but it still shares the terminal.
    """
    try:
        # Separate handles: a terminal isn't seekable, so text mode "r+" fails on it.
        with _TERMINAL.open("w") as out, _TERMINAL.open() as answer:
            _ = out.write(question)
            out.flush()
            return answer.readline().strip().lower() in _YES_ANSWERS
    except OSError as exc:
        logger.info("No terminal to ask on (%s); treating the answer as no", exc)
        return False


async def _ensure_current_schema() -> None:
    """Refuse to serve from a database that doesn't match schema.sql, unless the user resets it."""
    async with ops.get_db_context() as conn:
        match await schema_status(conn):
            case SchemaStatus.CURRENT:
                return
            case SchemaStatus.OUTDATED:
                problem = "schema.sql has changed since this database was built"
            case SchemaStatus.MISSING:
                problem = "this database has no Attenborough schema"
        question = f"\n{problem}.\nReset the database to schema.sql? This DELETES ALL DATA. [y/N] "
        if not await asyncio.to_thread(_confirm_on_terminal, question):
            raise RuntimeError(
                f"{problem}; refusing to start. To reset (deleting all data), run "
                + "`uv run python scripts/reset_db.py --yes` from api/, or start the server "
                + "from a terminal and answer the prompt."
            )
        await reset_schema(conn)
        logger.warning("Database reset to schema.sql; all previous data was deleted")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # The two tracked files a server start rewrites: the API spec and the settings template.
    openapi_json_path = Path(__file__).parent.parent / "openapi.json"
    _ = openapi_json_path.write_text(json.dumps(app.openapi()))
    logger.info("Wrote %s", openapi_json_path)
    write_example_env()

    await ops.db_conn_pool.open()
    try:
        # Before serving anything: the database must match schema.sql (api/README.md, "Database").
        await _ensure_current_schema()
        yield
    finally:
        await ops.db_conn_pool.close()


def _operation_id(route: APIRoute) -> str:
    """The route's namespaced name (e.g. "ip.get_ip_activity"), already unique and stable.

    It names the frontend's generated client functions (web/, hey-api), so FastAPI's default,
    which appends the path and method, would make them unreadable.
    """
    return route.name


app = FastAPI(
    responses=Message.for_statuses([HTTP_500_INTERNAL_SERVER_ERROR]),
    lifespan=lifespan,
    generate_unique_id_function=_operation_id,
)

app.add_middleware(TelemetryMiddleware)
# Added last so it runs first: telemetry and every handler see the real client address. Installing it
# here, not via uvicorn flags, applies the trust setting however the app is started.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.FORWARDED_ALLOW_IPS)


def include_routers(parent: FastAPI | Router, routers: Iterable[Router]):
    for router in routers:
        parent.include_router(router)


exhibit_router = ExhibitRouter(prefix="/exhibit")
include_routers(exhibit_router, exhibit_routers)
include_routers(app, honeypot_routers + [exhibit_router])


@app.get("/")
async def root():
    return JSONResponse(content={"content": "Hello, world!"})
