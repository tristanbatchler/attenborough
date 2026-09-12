import logging
import pathlib
from collections.abc import AsyncGenerator
from typing import LiteralString, cast

from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool

from attenborough import settings

file_path = pathlib.Path(__file__)

logger = logging.getLogger(file_path.name)

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


async def create_tables() -> None:
    schema_sql = (file_path.parent / "schema.sql").read_text()

    async with db_conn_pool.connection() as conn:
        async with conn.cursor() as cursor:
            _ = await cursor.execute(cast(LiteralString, schema_sql))

        await conn.commit()
    logger.info("db tables ready")
