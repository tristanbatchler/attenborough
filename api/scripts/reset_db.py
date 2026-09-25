"""Reset the application database to `schema.sql`, deleting all of its data.

Run from `api/`:

    uv run python scripts/reset_db.py --yes

This runs the same reset the server offers at startup when the database doesn't match
`schema.sql` (see `attenborough/db/schema.py`). It replaces the `public` schema in one transaction:
if `schema.sql` is broken, it rolls back and the database is left as it was. The database itself
must already exist. Connects through the app's own connection pool and `Settings`.
"""

import argparse
import asyncio
import sys

from attenborough.db import ops
from attenborough.db.schema import reset_schema, schema_status

CONFIRM_OPTION = "--yes"


async def reset() -> None:
    # The app's own pool and connection helper, opened just for this command.
    async with ops.db_conn_pool, ops.get_db_context() as conn:
        before = await schema_status(conn)
        await reset_schema(conn)
        after = await schema_status(conn)
    print(f"Database schema reset: {before} -> {after}")


class Args(argparse.Namespace):
    yes: bool = False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    _ = parser.add_argument(
        CONFIRM_OPTION,
        action="store_true",
        help="confirm that every row in the database may be destroyed",
    )
    args = parser.parse_args(namespace=Args())
    if not args.yes:
        parser.error(f"refusing to destroy the database without {CONFIRM_OPTION}")
    asyncio.run(reset())
    return 0


if __name__ == "__main__":
    sys.exit(main())
