"""The database schema: whether a database matches schema.sql, and resetting it to schema.sql.

A reset drops the `public` schema (every table, type and row), applies schema.sql, and records
schema.sql's SHA-256, all in one transaction: a broken schema.sql rolls back and leaves the
existing database untouched. There are no migrations; see api/README.md, "Database".
"""

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import LiteralString, cast

from psycopg import AsyncConnection
from psycopg.errors import UndefinedTable

from attenborough.db import queries

_SCHEMA_SQL = Path(__file__).with_name("schema.sql")


class SchemaStatus(StrEnum):
    CURRENT = "current"
    # Built from a different schema.sql: the file has changed since the last reset.
    OUTDATED = "outdated"
    # No schema_fingerprint table: never built by reset_schema (empty or foreign database).
    MISSING = "missing"


def _schema_sql() -> str:
    return _SCHEMA_SQL.read_text()


def _fingerprint(schema_sql: str) -> str:
    return hashlib.sha256(schema_sql.encode()).hexdigest()


async def schema_status(conn: AsyncConnection) -> SchemaStatus:
    """Compare the database with schema.sql. `conn` must be in autocommit mode."""
    try:
        recorded = await queries.get_schema_fingerprint(conn)
    except UndefinedTable:
        return SchemaStatus.MISSING
    if recorded == _fingerprint(_schema_sql()):
        return SchemaStatus.CURRENT
    return SchemaStatus.OUTDATED


async def reset_schema(conn: AsyncConnection) -> None:
    """Replace the database's schema and data with a fresh schema.sql, atomically."""
    schema_sql = _schema_sql()
    async with conn.transaction():
        await queries.drop_public_schema(conn)
        await queries.create_public_schema(conn)
        # schema.sql is a trusted file in this repository, never user input.
        _ = await conn.execute(cast(LiteralString, schema_sql))
        await queries.set_schema_fingerprint(conn, sha256=_fingerprint(schema_sql))
