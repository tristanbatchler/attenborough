from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool

from attenborough import settings

db_conn_info = make_conninfo(
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    user=settings.DB_USERNAME,
    password=settings.DB_PASSWORD,
    dbname=settings.DB_DATABASE,
)
db_conn_pool = AsyncConnectionPool(
    db_conn_info,
    open=False,
    min_size=settings.DB_MIN_POOL_SIZE,
    max_size=settings.DB_MAX_POOL_SIZE,
    timeout=settings.DB_POOL_TIMEOUT_SECONDS,
)


async def get_db_conn() -> AsyncGenerator[AsyncConnection]:
    async with db_conn_pool.connection() as conn:
        # Autocommit queries to run outside the usual `async with db_conn.transaction(): ...` block. This can be useful if
        # you are planning on throwing an exception later and don't want your query to roll back, e.g. in stashes password
        # attempt logging.
        await conn.set_autocommit(True)
        yield conn


def get_db_context():
    """This helps in the case that dependency injection is not available, e.g. in a middleware"""
    return asynccontextmanager(get_db_conn)()
