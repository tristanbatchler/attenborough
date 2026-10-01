"""The database schema: migrations, whether a database is up to date with them, and resets.

`migrations/` holds numbered SQL files (`0001_baseline.sql`, `0002_...`), applied in order, each in
its own transaction together with its row in `schema_migrations` (version, name and SHA-256). A
failed migration therefore rolls back and leaves the database as it was. `schema.sql` is what all
of them build, and src/tests/test_migrations.py checks that it is.

A development reset skips the migrations: it drops the `public` schema (every table, type and
row), applies schema.sql and records every migration as applied, in one transaction. Production
only ever migrates. See api/README.md, "Database".
"""

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import LiteralString, cast

from psycopg import AsyncConnection
from psycopg.errors import UndefinedTable

from attenborough.db import queries

_DB_DIRECTORY = Path(__file__).parent
SCHEMA_SQL = _DB_DIRECTORY / "schema.sql"
_MIGRATIONS_DIRECTORY = _DB_DIRECTORY / "migrations"
# `0002_add_geolocation.sql`: a four-digit version, then a name.
_MIGRATION_FILE = re.compile(r"(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql")
_SQL_GLOB = "*.sql"


class SchemaStatus(StrEnum):
    # Every migration applied, and none changed since.
    CURRENT = "current"
    # The applied migrations are the first ones, unchanged; the rest can be applied.
    PENDING = "pending"
    # An applied migration was edited or is unknown here: only a reset can fix it.
    DIVERGED = "diverged"
    # No schema_migrations table: an empty database, or one from before migrations.
    MISSING = "missing"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()

    @property
    def file_name(self) -> str:
        return f"{self.version:04d}_{self.name}.sql"


@cache
def migrations() -> tuple[Migration, ...]:
    """Every migration file, in order. Versions are numbered from 1 without gaps, so a missing or
    misnamed file stops the app rather than being skipped."""
    found: list[Migration] = []
    for path in sorted(_MIGRATIONS_DIRECTORY.glob(_SQL_GLOB)):
        match = _MIGRATION_FILE.fullmatch(path.name)
        if match is None:
            raise ValueError(
                f"{path.name}: migrations are named like 0001_baseline.sql"
            )
        found.append(Migration(int(match["version"]), match["name"], path.read_text()))
    for expected, migration in enumerate(found, start=1):
        if migration.version != expected:
            raise ValueError(
                f"{migration.file_name}: expected migration {expected:04d} next"
            )
    return tuple(found)


async def _applied(conn: AsyncConnection) -> list[tuple[int, str]] | None:
    """(version, sha256) of each applied migration in order; None without a schema_migrations
    table. `conn` must be in autocommit mode: the missing table's error would end a transaction."""
    try:
        rows = await queries.list_applied_migrations(conn)
    except UndefinedTable:
        return None
    return [(row.version, row.sha256) for row in rows]


def _pending(applied: list[tuple[int, str]]) -> tuple[Migration, ...] | None:
    """The migrations still to apply, or None if `applied` isn't a prefix of them."""
    known = [(migration.version, migration.sha256) for migration in migrations()]
    if applied != known[: len(applied)]:
        return None
    return migrations()[len(applied) :]


async def schema_status(conn: AsyncConnection) -> SchemaStatus:
    """Compare the database with the migrations. `conn` must be in autocommit mode."""
    applied = await _applied(conn)
    if applied is None:
        return SchemaStatus.MISSING
    pending = _pending(applied)
    if pending is None:
        return SchemaStatus.DIVERGED
    return SchemaStatus.PENDING if pending else SchemaStatus.CURRENT


async def pending_migrations(conn: AsyncConnection) -> tuple[Migration, ...]:
    """What `migrate` would apply. An empty database (no schema_migrations) needs all of them.
    Raises ValueError if the database has diverged from the migrations."""
    pending = _pending(await _applied(conn) or [])
    if pending is None:
        raise ValueError(
            "the database's applied migrations differ from migrations/; only a reset can fix it"
        )
    return pending


async def _record(conn: AsyncConnection, migration: Migration) -> None:
    await queries.record_migration(
        conn,
        version=migration.version,
        name=migration.name,
        sha256=migration.sha256,
    )


async def migrate(conn: AsyncConnection) -> tuple[Migration, ...]:
    """Apply the pending migrations in order, each in its own transaction, and return them.
    `conn` must be in autocommit mode."""
    pending = await pending_migrations(conn)
    for migration in pending:
        async with conn.transaction():
            # Migration files are trusted files in this repository, never user input.
            _ = await conn.execute(cast(LiteralString, migration.sql))
            await _record(conn, migration)
    return pending


async def reset_schema(conn: AsyncConnection) -> None:
    """Replace the database's schema and data with a fresh schema.sql, atomically, recording every
    migration as applied (schema.sql is what they build)."""
    async with conn.transaction():
        await queries.drop_public_schema(conn)
        await queries.create_public_schema(conn)
        # schema.sql is a trusted file in this repository, never user input.
        _ = await conn.execute(cast(LiteralString, SCHEMA_SQL.read_text()))
        for migration in migrations():
            await _record(conn, migration)
