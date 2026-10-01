"""schema.sql and the migrations must build the same schema: sqlc generates the code from
schema.sql, while production databases are built by the migrations.

This needs the development database (api/.env), and leaves no trace in it: both schemas are built
side by side in scratch schemas, inside one transaction that is always rolled back.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import LiteralString, cast

import pytest
from psycopg import AsyncConnection, sql
from psycopg.rows import class_row

from attenborough.db import schema
from attenborough.db.ops import db_conn_pool

_BUILT_BY_MIGRATIONS = "check_migrations"
_BUILT_BY_SCHEMA_SQL = "check_schema_sql"

# Every object in the current schema as one line of text, with the schema's own name removed so
# that two schemas compare equal. Columns carry their position: generated rows are positional, so
# a column a migration appends must come last in schema.sql too.
_CATALOG = """
SELECT replace(line, current_schema() || '.', '') AS line FROM (
    SELECT format('column %s.%s #%s %s not null=%s default=%s identity=%s',
                  c.relname, a.attname, a.attnum, format_type(a.atttypid, a.atttypmod),
                  a.attnotnull, pg_get_expr(d.adbin, d.adrelid), a.attidentity) AS line
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE c.relnamespace = current_schema()::regnamespace AND c.relkind IN ('r', 'v')
      AND a.attnum > 0 AND NOT a.attisdropped
    UNION ALL
    SELECT format('constraint %s %s %s', conrelid::regclass, conname, pg_get_constraintdef(oid))
    FROM pg_constraint WHERE connamespace = current_schema()::regnamespace
    UNION ALL
    SELECT format('index %s', pg_get_indexdef(indexrelid))
    FROM pg_index JOIN pg_class c ON c.oid = indexrelid
    WHERE c.relnamespace = current_schema()::regnamespace
    UNION ALL
    SELECT format('view %s %s', relname, pg_get_viewdef(oid))
    FROM pg_class WHERE relnamespace = current_schema()::regnamespace AND relkind = 'v'
    UNION ALL
    SELECT format('sequence %s', relname)
    FROM pg_class WHERE relnamespace = current_schema()::regnamespace AND relkind = 'S'
    UNION ALL
    SELECT format('function %s', pg_get_functiondef(p.oid))
    FROM pg_proc p WHERE pronamespace = current_schema()::regnamespace
    UNION ALL
    SELECT format('trigger %s', pg_get_triggerdef(t.oid))
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
    WHERE c.relnamespace = current_schema()::regnamespace AND NOT t.tgisinternal
    UNION ALL
    SELECT format('enum %s %s', t.typname, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder))
    FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
    WHERE t.typnamespace = current_schema()::regnamespace
    GROUP BY t.typname
) catalog
ORDER BY line
"""


@dataclass
class CatalogLine:
    line: str


async def _build(conn: AsyncConnection, name: str, ddl: Iterable[str]) -> list[str]:
    """Apply `ddl` in a new schema `name` (public stays on the path, for its extensions) and
    describe what it built."""
    schema_name = sql.Identifier(name)
    _ = await conn.execute(sql.SQL("CREATE SCHEMA {}").format(schema_name))
    _ = await conn.execute(
        sql.SQL("SET LOCAL search_path TO {}, public").format(schema_name)
    )
    for statements in ddl:
        # Trusted files in this repository.
        _ = await conn.execute(cast(LiteralString, statements))
    async with conn.cursor(row_factory=class_row(CatalogLine)) as cursor:
        _ = await cursor.execute(_CATALOG)
        return [row.line for row in await cursor.fetchall()]


@pytest.mark.anyio
async def test_the_migrations_build_schema_sql():
    async with (
        db_conn_pool,
        db_conn_pool.connection() as conn,
        conn.transaction(force_rollback=True),
    ):
        by_migrations = await _build(
            conn,
            _BUILT_BY_MIGRATIONS,
            (migration.sql for migration in schema.migrations()),
        )
        by_schema_sql = await _build(
            conn, _BUILT_BY_SCHEMA_SQL, [schema.SCHEMA_SQL.read_text()]
        )
    assert by_migrations == by_schema_sql
    # A broken catalog query would compare two empty lists.
    assert by_schema_sql
