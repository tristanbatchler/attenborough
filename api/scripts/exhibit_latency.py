"""Time every page of an exhibit listing, first to last, against a running API.

Run from `api/` with the server running (and, to mean anything, a large database such as one
filled by `scripts/seed_db.py`), or in a deployment, where the API is reachable only from inside its
container: `docker compose exec api python scripts/exhibit_latency.py --base-url http://127.0.0.1:8000`.

    uv run python scripts/exhibit_latency.py                          # the feed
    uv run python scripts/exhibit_latency.py --address 198.18.0.0     # one address's activity

It follows each page's `next_cursor` until the last page, as a reader paging back would, timing
each request and the address's summary. Measure where the API and the database are close: over a
slow network link (Wi-Fi), each page's few round trips dominate. Standard library only, so that it
runs in the container image, which has no development dependencies. Prints the number of pages, the median, 95th percentile
and slowest time, and exits 1 if any page took longer than `--limit-ms`. Read-only.
"""

import argparse
import statistics
import sys
import time
from http import HTTPMethod, HTTPStatus
from http.client import HTTPConnection
from urllib.parse import urlencode, urlsplit

from attenborough.events import EventPage

DEFAULT_API_URL = "http://127.0.0.1:8765"
DEFAULT_TAKE = 200
DEFAULT_LIMIT_MS = 100
FEED_PATH = "/exhibit/feed"
BEFORE_PARAM = "before"
TAKE_PARAM = "take"
PERCENTILES = 20


class Args(argparse.Namespace):
    base_url: str = DEFAULT_API_URL
    address: str | None = None
    take: int = DEFAULT_TAKE
    limit_ms: float = DEFAULT_LIMIT_MS


def timed_get(
    base_url: str, path: str, params: dict[str, str | int]
) -> tuple[float, bytes]:
    """The response body and how long it took, in milliseconds. Raises on any status but 200."""
    url = urlsplit(base_url)
    connection = HTTPConnection(url.netloc)
    started = time.perf_counter()
    connection.request(HTTPMethod.GET, f"{path}?{urlencode(params)}")
    response = connection.getresponse()
    body = response.read()
    elapsed = (time.perf_counter() - started) * 1000
    connection.close()
    if response.status != HTTPStatus.OK:
        raise RuntimeError(f"{path}: HTTP {response.status}")
    return elapsed, body


def walk(base_url: str, path: str, take: int) -> list[float]:
    """Each page's time, newest page first."""
    times: list[float] = []
    params: dict[str, str | int] = {TAKE_PARAM: take}
    while True:
        elapsed, body = timed_get(base_url, path, params)
        times.append(elapsed)
        cursor = EventPage.model_validate_json(body).next_cursor
        if cursor is None:
            return times
        params[BEFORE_PARAM] = cursor


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    _ = parser.add_argument("--base-url", default=Args.base_url)
    _ = parser.add_argument("--address", help="one IP address's listing, not the feed")
    _ = parser.add_argument("--take", type=int, default=Args.take)
    _ = parser.add_argument("--limit-ms", type=float, default=Args.limit_ms)
    args = parser.parse_args(namespace=Args())

    if args.address is None:
        listing = FEED_PATH
    else:
        listing = f"/exhibit/ip/{args.address}/activity"
        summary_ms, _ = timed_get(
            args.base_url, f"/exhibit/ip/{args.address}/summary", {}
        )
        print(f"summary: {summary_ms:.1f} ms")
    times = walk(args.base_url, listing, args.take)

    slowest = max(times)
    print(
        f"{listing}: {len(times)} pages of {args.take}, median {statistics.median(times):.1f} ms, "
        + f"p95 {statistics.quantiles(times, n=PERCENTILES)[-1] if len(times) > 1 else slowest:.1f} ms, "
        + f"slowest {slowest:.1f} ms (page {times.index(slowest) + 1})"
    )
    return 0 if slowest <= args.limit_ms else 1


if __name__ == "__main__":
    sys.exit(main())
