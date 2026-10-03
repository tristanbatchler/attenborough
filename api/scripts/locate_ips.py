"""Locate every address that visited the honeypot but was never located: those recorded before
geolocation was set up, or while GEOIP_DIRECTORY was unset. New visitors are located as their first
request is recorded, so this is needed once, after turning geolocation on.

Run from `api/` (`uv run python scripts/locate_ips.py`), or in a deployment, inside the API's
container, which has the databases mounted: `docker compose exec api python scripts/locate_ips.py`.
Each address gets the databases' current answer, with their dates (geolocation.py). Safe to run
again: located addresses are skipped. Connects through the app's own pool and `Settings`.
"""

import argparse
import asyncio
import sys

from attenborough import settings
from attenborough.db import queries
from attenborough.db.ops import db_conn_pool
from attenborough.geolocation import geolocator, record_location


async def run() -> int:
    if settings.GEOIP_DIRECTORY is None:
        print("GEOIP_DIRECTORY is not set: nothing to locate with", file=sys.stderr)
        return 1
    with geolocator:
        async with db_conn_pool, db_conn_pool.connection() as conn:
            addresses = await queries.list_unlocated_addresses(conn)
            for address in addresses:
                await record_location(conn, address)
    print(f"Located {len(addresses)} addresses")
    return 0


def main() -> int:
    _ = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
