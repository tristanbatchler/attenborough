from collections.abc import Sequence

from attenborough.db import queries
from attenborough.dependencies import DBConn, PagingQuery
from attenborough.router import ExhibitRouter
from attenborough.router.group import RouterGroup

router = ExhibitRouter(prefix="/feed")


@router.get("", response_model=Sequence[queries.ListRecentActivityRow])
async def list_recent(
    db_conn: DBConn, paging: PagingQuery
) -> Sequence[queries.ListRecentActivityRow]:
    """The latest visitor activity from every IP address, newest first."""
    return await queries.list_recent_activity(
        db_conn,
        router_group=RouterGroup.HONEYPOT,
        offset=paging.offset,
        limit=paging.take,
    )
