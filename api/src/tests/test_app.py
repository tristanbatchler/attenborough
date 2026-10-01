from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from http import HTTPMethod, HTTPStatus

import pytest
from fastapi.openapi.utils import get_openapi
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ValidationError

from attenborough import telemetry
from attenborough.db import queries
from attenborough.db.enums import EventKind, RouterGroup
from attenborough.db.ops import get_db_conn
from attenborough.events import FIRST_PAGE, EventCursor
from attenborough.exhibit import Paging
from attenborough.main import app

# The parametrized arguments.
REQUEST = "method, path, status, group"
TAKE = "take, fetched, expected_next"
AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
IP = "203.0.113.7"


def test_operation_ids_are_unique():
    # Operation IDs are the route functions' names, and name the generated clients' functions.
    # Built afresh, not from app.openapi()'s cache, so that FastAPI's "Duplicate Operation ID"
    # warning (an error under pytest's filterwarnings) fires if two routes share a name.
    _ = get_openapi(title=app.title, version=app.version, routes=app.routes)


class RecordedHit(BaseModel):
    router_group: RouterGroup
    status_code: int
    path: str


@pytest.fixture
async def recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[list[RecordedHit]]:
    """What the middleware would record, without a database. Only telemetry_probe.py verify proves
    that rows really land; this pins down the classification."""
    hits: list[RecordedHit] = []

    async def record_hit(
        *, router_group: RouterGroup, status_code: int, path: str, **_: object
    ) -> None:
        hits.append(
            RecordedHit(router_group=router_group, status_code=status_code, path=path)
        )

    async def no_db_conn() -> AsyncGenerator[None]:
        yield None

    monkeypatch.setattr(telemetry, record_hit.__name__, record_hit)
    app.dependency_overrides[get_db_conn] = no_db_conn
    yield hits
    app.dependency_overrides.clear()


@pytest.mark.anyio
@pytest.mark.parametrize(
    REQUEST,
    [
        # Nothing matched: a scanner probing the API itself.
        (HTTPMethod.GET, "/wp-login.php", HTTPStatus.NOT_FOUND, RouterGroup.HONEYPOT),
        (HTTPMethod.GET, "/docs", HTTPStatus.OK, RouterGroup.SYSTEM),
        (HTTPMethod.GET, "/openapi.json", HTTPStatus.OK, RouterGroup.SYSTEM),
        (
            HTTPMethod.GET,
            "/exhibit/ip/not-an-ip/activity",
            HTTPStatus.UNPROCESSABLE_ENTITY,
            RouterGroup.EXHIBIT,
        ),
        # Larger than a BIGINT: rejected, not passed to the database.
        (
            HTTPMethod.GET,
            "/exhibit/hits/9223372036854775808",
            HTTPStatus.UNPROCESSABLE_ENTITY,
            RouterGroup.EXHIBIT,
        ),
        (
            HTTPMethod.DELETE,
            "/exhibit/feed",
            HTTPStatus.METHOD_NOT_ALLOWED,
            RouterGroup.EXHIBIT,
        ),
        # The decoy app's reports are records of other requests, never recorded themselves.
        (HTTPMethod.POST, "/ingest/hits", HTTPStatus.UNPROCESSABLE_ENTITY, None),
    ],
)
async def test_every_request_is_recorded_once_by_group(
    recorded: list[RecordedHit],
    method: HTTPMethod,
    path: str,
    status: HTTPStatus,
    group: RouterGroup | None,
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(method, path)
    assert response.status_code == status
    expected = (
        []
        if group is None
        else [RecordedHit(router_group=group, status_code=status, path=path)]
    )
    assert recorded == expected


def _event(n: int) -> queries.ListRecentEventsRow:
    return queries.ListRecentEventsRow(
        kind=EventKind.HIT, id_=n, ip_address=IP, occurred_at=AT - timedelta(seconds=n)
    )


@pytest.mark.parametrize(
    TAKE,
    [
        (2, 3, True),
        (2, 2, False),
        (2, 0, False),
    ],
)
def test_a_page_is_take_rows_and_the_extra_row_means_more(
    take: int, fetched: int, expected_next: bool
):
    paging = Paging(take=take)
    assert paging.limit == take + 1
    rows = [_event(n) for n in range(1, fetched + 1)]
    token = paging.next_cursor(rows)
    assert (token is not None) is expected_next
    if token is not None:
        # The next page starts after the page's last row, not after the extra one.
        assert EventCursor.from_token(token) == EventCursor.after(rows[take - 1])


def test_the_first_page_starts_after_every_event():
    assert Paging().cursor == FIRST_PAGE
    assert FIRST_PAGE.occurred_at > datetime.now(tz=UTC)


@pytest.mark.parametrize(
    "token",
    [
        "not base64!",
        # Base64, but not a cursor.
        "eyJhIjogMX0=",
        EventCursor(occurred_at=AT, kind=EventKind.HIT, id=1).token()[:-4],
    ],
)
def test_a_cursor_that_this_api_did_not_make_is_rejected(token: str):
    with pytest.raises(ValidationError):
        _ = Paging(before=token)
