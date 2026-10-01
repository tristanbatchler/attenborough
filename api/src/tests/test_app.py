from collections.abc import AsyncGenerator
from http import HTTPMethod, HTTPStatus

import pytest
from fastapi.openapi.utils import get_openapi
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from attenborough import telemetry
from attenborough.db.enums import RouterGroup
from attenborough.db.ops import get_db_conn
from attenborough.exhibit import Paging
from attenborough.main import app

# The parametrized arguments.
REQUEST = "method, path, status, group"
TAKE = "take, fetched, expected_items, expected_has_next"


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


@pytest.mark.parametrize(
    TAKE,
    [
        (2, 3, 2, True),
        (2, 2, 2, False),
        (2, 0, 0, False),
    ],
)
def test_a_page_is_take_rows_and_the_extra_row_means_more(
    take: int, fetched: int, expected_items: int, expected_has_next: bool
):
    paging = Paging(take=take)
    assert paging.limit == take + 1
    items, has_next = paging.page_of(range(fetched))
    assert len(items) == expected_items
    assert has_next is expected_has_next
