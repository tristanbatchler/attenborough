from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from http import HTTPMethod, HTTPStatus

import pytest
from fastapi.openapi.utils import get_openapi
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, JsonValue, ValidationError

from attenborough import admin, auth, exhibit, telemetry
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
EMAIL = "admin@example.org"


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
        # Without a session, the admin area is a 404, like an unknown path, before any body is read.
        # Never recorded: its requests carry the session token.
        *(
            (method, path, HTTPStatus.NOT_FOUND, None)
            for method, path in [
                (HTTPMethod.GET, "/auth/me"),
                (HTTPMethod.POST, "/auth/logout"),
                (HTTPMethod.GET, "/admin/bans"),
                (HTTPMethod.GET, f"/admin/ip/{IP}/bans"),
                (HTTPMethod.POST, f"/admin/ip/{IP}/bans"),
                (HTTPMethod.POST, "/admin/bans/1/revoke"),
                (HTTPMethod.GET, "/admin/audit"),
                (HTTPMethod.GET, "/admin/rules"),
                (HTTPMethod.POST, "/admin/rules"),
                (HTTPMethod.GET, "/admin/rules/1"),
                (HTTPMethod.POST, "/admin/rules/1/move"),
                (HTTPMethod.POST, "/admin/rules/preview"),
            ]
        ),
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


# The admin area's own models: none may be reachable from a public response.
_ADMIN_MODELS = {
    model.__name__
    for model in (
        admin.BanRecord,
        admin.RuleRecord,
        admin.Preview,
        admin.AuditEntry,
        auth.Me,
        auth.Session,
        auth.GoogleLogin,
    )
}


class _Operation(BaseModel):
    responses: dict[str, JsonValue]


class _Components(BaseModel):
    schemas: dict[str, JsonValue]


class _Spec(BaseModel):
    """The parts of the OpenAPI document that say which models each route returns."""

    paths: dict[str, dict[str, _Operation]]
    components: _Components


def _refs(schema: JsonValue) -> set[str]:
    """The names of the models a piece of the OpenAPI document refers to."""
    match schema:
        case {"$ref": str(ref)}:
            return {ref.rsplit("/", 1)[-1]}
        case dict():
            return {name for value in schema.values() for name in _refs(value)}
        case list():
            return {name for value in schema for name in _refs(value)}
        case _:
            return set()


def test_no_public_response_reaches_admin_data():
    spec = _Spec.model_validate(
        get_openapi(title=app.title, version=app.version, routes=app.routes)
    )
    models = spec.components.schemas
    pending = {
        name
        for path, operations in spec.paths.items()
        if path.startswith(exhibit.router.prefix)
        for operation in operations.values()
        for name in _refs(operation.responses)
    }
    reached: set[str] = set()
    while pending:
        name = pending.pop()
        reached.add(name)
        pending |= _refs(models[name]) - reached
    assert _ADMIN_MODELS <= set(models)
    assert not reached & _ADMIN_MODELS


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


@pytest.mark.anyio
async def test_fixed_paths_reach_their_routes(recorded: list[RecordedHit]):
    # A fixed path declared after a parameterised one (/rules/{rule_id}) would be taken by it: an
    # empty preview would then fail on the rule id in its path, not on its missing rule.
    def an_admin() -> auth.AdminSession:
        return auth.AdminSession(user_id=1, email=EMAIL, name=EMAIL, token_hash="")

    app.dependency_overrides[auth.current_admin] = an_admin
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        markers = await client.get("/admin/rules/markers")
        preview = await client.post("/admin/rules/preview", json={})
    assert markers.status_code == HTTPStatus.OK
    assert preview.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert ValidationErrors.model_validate_json(preview.content).detail[0].loc[:2] == [
        "body",
        "rule",
    ]
    assert recorded == []


class _ValidationError(BaseModel):
    loc: list[str | int]


class ValidationErrors(BaseModel):
    detail: list[_ValidationError]
