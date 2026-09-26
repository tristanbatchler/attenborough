from collections.abc import Sequence

from pydantic import IPvAnyAddress
from starlette.status import HTTP_404_NOT_FOUND

from attenborough.db import queries
from attenborough.dependencies import DBConn, PagingQuery
from attenborough.response_models import Message
from attenborough.router import ExhibitRouter
from attenborough.router.group import RouterGroup

router = ExhibitRouter(prefix="/ip")


@router.get(
    "/{ip_addr}/activity",
    response_model=Sequence[queries.ListIpActivityRow],
    responses=Message.for_statuses([HTTP_404_NOT_FOUND]),
)
async def get_ip_activity(
    ip_addr: IPvAnyAddress, db_conn: DBConn, paging: PagingQuery
) -> Sequence[queries.ListIpActivityRow]:
    return await queries.list_ip_activity(
        db_conn,
        ip_address=str(ip_addr),
        router_group=RouterGroup.HONEYPOT,
        offset=paging.offset,
        limit=paging.take,
    )
