"""Apply the pending migrations (`src/attenborough/db/migrations/`) to the application database.

Run from `api/` as the schema's owner, never as the app's own role, which can't change the schema:

    DB_USERNAME=<owner> DB_PASSWORD=<password> uv run python scripts/migrate.py

In a deployment: `docker compose run --rm migrate` (see api/README.md, "Database"). Each migration
runs in its own transaction with its schema_migrations row, so a failure leaves the database at the
last migration that succeeded. A new, empty database gets every migration. A database whose applied
migrations differ from the files is refused: only a reset fixes that, and resets are for
development. Connects through the app's own connection pool and `Settings`.
"""

import argparse
import asyncio
import sys

from attenborough.db.ops import db_conn_pool
from attenborough.db.schema import migrate, schema_status


async def run() -> int:
    async with db_conn_pool, db_conn_pool.connection() as conn:
        before = await schema_status(conn)
        try:
            applied = await migrate(conn)
        except ValueError as exc:
            print(f"Refusing to migrate: {exc}", file=sys.stderr)
            return 1
        after = await schema_status(conn)
    for migration in applied:
        print(f"Applied {migration.file_name}")
    print(f"Database schema: {before} -> {after}")
    return 0


def main() -> int:
    _ = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
