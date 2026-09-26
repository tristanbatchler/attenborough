from collections.abc import Sequence
from typing import Annotated

from fastapi import Query
from pydantic import IPvAnyAddress
from starlette.status import HTTP_404_NOT_FOUND

from attenborough import settings
from attenborough.db import queries
from attenborough.dependencies import DBConn
from attenborough.response_models import Message
from attenborough.router import ExhibitRouter

router = ExhibitRouter(prefix="/ip")


@router.get(
    "/{ip_addr}/activity",
    response_model=Sequence[queries.ListIpActivityRow],
    responses=Message.for_statuses([HTTP_404_NOT_FOUND]),
)
async def get_ip_activity(
    ip_addr: IPvAnyAddress,
    db_conn: DBConn,
    page: Annotated[int, Query(ge=1)] = 1,
    take: Annotated[
        int, Query(ge=1, le=settings.APP_MAX_PAGE_TAKE)
    ] = settings.APP_DEFAULT_PAGE_TAKE,
) -> Sequence[queries.ListIpActivityRow]:
    ip_activity = await queries.list_ip_activity(
        db_conn, ip_address=str(ip_addr), offset=(page - 1) * take, limit=take
    )
    return ip_activity
