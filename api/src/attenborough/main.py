import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from attenborough import exhibit, ingest, settings
from attenborough.db.ops import db_conn_pool
from attenborough.db.schema import (
    SchemaStatus,
    migrate,
    pending_migrations,
    reset_schema,
    schema_status,
)
from attenborough.dependencies import RequestOrigin
from attenborough.settings import SOURCE_CHECKOUT, write_example_env
from attenborough.telemetry import TelemetryMiddleware

logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)

logger = logging.getLogger(__name__)

_TERMINAL = Path("/dev/tty")
_YES_ANSWERS = frozenset({"y", "yes"})
# The API spec, written at every start; the web and decoy clients are generated from it.
_OPENAPI_JSON = Path(__file__).parent.parent / "openapi.json"


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
    """Refuse to serve from a database that isn't up to date with the migrations, unless the user
    migrates or resets it on the terminal. Without a terminal (a container), it refuses and logs why.
    """
    async with db_conn_pool.connection() as conn:
        match await schema_status(conn):
            case SchemaStatus.CURRENT:
                return
            case SchemaStatus.PENDING:
                names = ", ".join(m.file_name for m in await pending_migrations(conn))
                question = f"\nThis database needs migrations: {names}.\nApply them now? [y/N] "
                if not await asyncio.to_thread(_confirm_on_terminal, question):
                    raise RuntimeError(
                        f"the database needs migrations ({names}); refusing to start. Apply them "
                        + "as the schema owner: `uv run python scripts/migrate.py` from api/, or "
                        + "`docker compose run --rm migrate` in a deployment (api/README.md)."
                    )
                applied = await migrate(conn)
                logger.warning("Applied %d migrations", len(applied))
                return
            case SchemaStatus.DIVERGED:
                problem = "this database's applied migrations differ from migrations/"
            case SchemaStatus.MISSING:
                problem = "this database has no Attenborough schema"
        question = f"\n{problem}.\nReset the database to schema.sql? This DELETES ALL DATA. [y/N] "
        if not await asyncio.to_thread(_confirm_on_terminal, question):
            raise RuntimeError(
                f"{problem}; refusing to start. A new, empty database is set up with "
                + "`scripts/migrate.py` (`docker compose run --rm migrate`). To reset a "
                + "development database (deleting all data), run "
                + "`uv run python scripts/reset_db.py --yes` from api/, or start the server "
                + "from a terminal and answer the prompt."
            )
        await reset_schema(conn)
        logger.warning("Database reset to schema.sql; all previous data was deleted")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # The two tracked files a server start rewrites in a source checkout: the API spec and the
    # settings template. An installed package (the container image) has neither to update.
    if SOURCE_CHECKOUT:
        _ = _OPENAPI_JSON.write_text(json.dumps(app.openapi()))
        logger.info("Wrote %s", _OPENAPI_JSON)
        write_example_env()

    async with db_conn_pool:
        # Before serving anything: the database must be up to date (api/README.md, "Database").
        await _ensure_current_schema()
        yield


def _operation_id(route: APIRoute) -> str:
    """The route's function name (e.g. "get_ip_activity"), which must be unique across the API.

    It names the generated clients' functions (getIpActivity), so FastAPI's default, which
    appends the path and method, would make them unreadable.
    """
    return route.name


app = FastAPI(lifespan=lifespan, generate_unique_id_function=_operation_id)

app.add_middleware(TelemetryMiddleware)
# Added last so it runs first: telemetry and every handler see the real client address. Installing it
# here, not via uvicorn flags, applies the trust setting however the app is started.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.FORWARDED_ALLOW_IPS)

app.include_router(exhibit.router)
app.include_router(ingest.router)

# Development only. Left out of the OpenAPI spec so that openapi.json (tracked, and rewritten at
# startup) doesn't depend on the setting.
if settings.DEBUG:

    @app.get("/test", include_in_schema=False)
    async def test(request_origin: RequestOrigin) -> dict[str, str]:
        """The server's view of the request: whom it attributes the request to, and when."""
        return {
            "server_time": datetime.now(tz=UTC).isoformat(),
            "request_origin": str(request_origin),
        }
