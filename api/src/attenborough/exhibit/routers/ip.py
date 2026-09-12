from starlette.status import HTTP_404_NOT_FOUND
from typing import Sequence
from attenborough.response_models import Message
from attenborough.router import Router
from attenborough.db import queries
from attenborough.dependencies import DBConn
from attenborough import settings

router = Router(prefix="/ip")

@router.get("/{ip_addr}/activity", response_model=Sequence[queries.ListIpActivityRow], responses=Message.for_statuses([HTTP_404_NOT_FOUND]))
async def get_ip_activity(ip_addr: str, db_conn: DBConn, page: int = 1, take: int = settings.APP_DEFAULT_PAGE_TAKE) -> Sequence[queries.ListIpActivityRow]:
    ip_activity = await queries.list_ip_activity(db_conn, ip_address=ip_addr, offset=(page - 1) * take, limit=take)
    return ip_activity