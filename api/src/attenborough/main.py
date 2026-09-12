from collections.abc import Iterable

from fastapi import FastAPI
from starlette.responses import JSONResponse

from attenborough.router import Router

app = FastAPI()


def include_routers(parent: FastAPI | Router, routers: Iterable[Router]):
    for router in routers:
        parent.include_router(router)


from attenborough.exhibit.routers import exported_routers as exhibit_routers
from attenborough.honeypot.routers import exported_routers as honeypot_routers

exhibit_router = Router(prefix="/exhibit")
include_routers(exhibit_router, exhibit_routers)
include_routers(app, honeypot_routers + [exhibit_router])


@app.get("/")
async def root():
    return JSONResponse(content=f'{"content": "Hello, world!"}')
