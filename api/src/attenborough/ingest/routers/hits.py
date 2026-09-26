from fastapi import BackgroundTasks
from starlette.status import HTTP_204_NO_CONTENT

from attenborough.dependencies import RequestOrigin
from attenborough.ingest.models import DecoyHit
from attenborough.router import IngestRouter
from attenborough.router.group import RouterGroup
from attenborough.telemetry import record_hit

router = IngestRouter(prefix="/hits")


@router.post("", status_code=HTTP_204_NO_CONTENT)
async def record_decoy_hit(
    hit: DecoyHit, origin: RequestOrigin, background_tasks: BackgroundTasks
) -> None:
    """Record a request the decoy app served. The visitor is `origin`: the decoy app names them in
    X-Forwarded-For, which only counts because its address is in FORWARDED_ALLOW_IPS.

    Written after this response, so the decoy app waits only for the round trip, not the database.
    """
    background_tasks.add_task(
        record_hit,
        ip_address=str(origin),
        method=hit.method,
        path=hit.path,
        query=hit.query,
        router_group=RouterGroup.HONEYPOT,
        headers=hit.headers,
        body=hit.body,
        status_code=hit.status_code,
    )
