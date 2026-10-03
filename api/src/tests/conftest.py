from collections.abc import AsyncGenerator

import pytest
from psycopg import AsyncConnection

from attenborough.db.ops import db_conn_pool

# The fixtures' scope: one for the whole test run.
SESSION = "session"


@pytest.fixture(scope=SESSION)
def anyio_backend() -> str:
    """Session-wide, so that `db_conn` can be too."""
    return "asyncio"


@pytest.fixture(scope=SESSION)
async def db_conn() -> AsyncGenerator[AsyncConnection]:
    """A connection to the development database (api/.env), for the tests that need PostgreSQL.

    One for the whole session: the app's pool can't be reopened once closed. Tests leave no trace
    in the database: they only read, or work inside a transaction they roll back.
    """
    async with db_conn_pool, db_conn_pool.connection() as conn:
        yield conn
