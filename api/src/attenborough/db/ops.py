from collections.abc import AsyncGenerator

from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool

from attenborough import settings

# The one source of database connections. Every connection is in autocommit mode: each query
# commits on its own, and `async with conn.transaction():` groups queries where that matters.
# Code outside a request (startup, middleware, scripts) borrows with `db_conn_pool.connection()`.
db_conn_pool = AsyncConnectionPool(
    make_conninfo(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USERNAME,
        password=settings.DB_PASSWORD,
        dbname=settings.DB_DATABASE,
    ),
    kwargs={"autocommit": True},
    open=False,
    min_size=settings.DB_MIN_POOL_SIZE,
    max_size=settings.DB_MAX_POOL_SIZE,
    timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    # Test each connection as it is handed out and replace it if dead. Pooled connections can be
    # closed by the server or network while idle (e.g. overnight); without this, the next request
    # on each one fails with a 500 and loses its telemetry row. Costs one round trip per borrow.
    check=AsyncConnectionPool.check_connection,
)


async def get_db_conn() -> AsyncGenerator[AsyncConnection]:
    """The request handlers' connection (the `DBConn` dependency)."""
    async with db_conn_pool.connection() as conn:
        yield conn
