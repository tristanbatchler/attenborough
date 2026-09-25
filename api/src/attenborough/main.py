import json
import logging
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from attenborough.db import ops
from attenborough.exhibit.routers import exported_routers as exhibit_routers
from attenborough.honeypot.routers import exported_routers as honeypot_routers
from attenborough.middleware import TelemetryMiddleware
from attenborough.response_models import Message
from attenborough.router import ExhibitRouter, Router

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(name="attenborough")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    openapi_json_path = Path(__file__).parent.parent / "openapi.json"
    _ = openapi_json_path.write_text(json.dumps(app.openapi()))
    logger.info("Wrote %s", openapi_json_path)

    await ops.db_conn_pool.open()
    await ops.create_tables()
    yield
    await ops.db_conn_pool.close()


app = FastAPI(
    responses=Message.for_statuses([HTTP_500_INTERNAL_SERVER_ERROR]),
    lifespan=lifespan,
)

app.add_middleware(TelemetryMiddleware)


def include_routers(parent: FastAPI | Router, routers: Iterable[Router]):
    for router in routers:
        parent.include_router(router)


exhibit_router = ExhibitRouter(prefix="/exhibit")
include_routers(exhibit_router, exhibit_routers)
include_routers(app, honeypot_routers + [exhibit_router])


@app.get("/")
async def root():
    return JSONResponse(content={"content": "Hello, world!"})
