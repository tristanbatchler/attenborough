from datetime import UTC, datetime
from http import HTTPMethod

import pytest

from attenborough.db import enums, models, queries
from attenborough.db.enums import EventKind
from attenborough.events import (
    DISCRIMINATOR,
    DecoyPasswordAttemptEvent,
    DecoyViewEvent,
    HitEvent,
    LoginAttemptEvent,
    decode_body,
    decoy_password_attempt_event,
    decoy_view_event,
    hit_detail,
    hit_event,
    in_page_order,
    ip_summary,
    login_attempt_event,
)

AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
IP = "203.0.113.7"
PATH = "/wp-login.php"
PREVIEW = "body, preview, size, truncated"
QUERY = "a=1"
USER_AGENT = "curl/8"
USERNAME = "admin"
PASSWORD = "hunter2"
DOWNLOAD = "backup.zip"
NOTE = "notes"


def hit_row(body_preview: bytes, body_size: int | None) -> queries.GetHitsByIdsRow:
    return queries.GetHitsByIdsRow(
        id_=1,
        ip_address=IP,
        occurred_at=AT,
        method=HTTPMethod.POST,
        path=PATH,
        query=QUERY,
        status_code=200,
        user_agent=USER_AGENT,
        body_preview=memoryview(body_preview),
        body_size=body_size,
    )


@pytest.mark.parametrize(
    PREVIEW,
    [
        # Readable text stays readable.
        (b"log=root&pwd=hunter2", "log=root&pwd=hunter2", 20, False),
        (b"caf\xc3\xa9", "café", 5, False),
        # Bytes that aren't UTF-8 show as \xNN, never replaced or dropped.
        (b"\xff\xfeok", "\\xff\\xfeok", 4, False),
        # Longer than the preview: body_size says so.
        (b"a" * 1024, "a" * 1024, 70_000, True),
        # No body captured: null, not empty.
        (b"", None, None, False),
    ],
)
def test_a_hit_body_preview_is_decoded_as_received(
    body: bytes, preview: str | None, size: int | None, truncated: bool
):
    event = hit_event(hit_row(body, size))
    assert event.body_preview == preview
    assert event.body_size == size
    assert event.body_truncated is truncated


def test_an_empty_captured_body_is_empty_not_null():
    assert hit_event(hit_row(b"", 0)).body_preview == ""


def test_a_hit_maps_every_field():
    assert hit_event(hit_row(b"x", 1)) == HitEvent(
        kind=EventKind.HIT,
        id=1,
        occurred_at=AT,
        ip_address=IP,
        method=HTTPMethod.POST,
        path=PATH,
        query=QUERY,
        status_code=200,
        user_agent=USER_AGENT,
        body_preview="x",
        body_size=1,
        body_truncated=False,
    )


def test_a_hit_detail_has_its_headers_and_whole_body():
    detail = hit_detail(
        queries.GetHitRow(
            id_=1,
            ip_address=IP,
            occurred_at=AT,
            method="GET",
            path=PATH,
            query=None,
            status_code=404,
            user_agent=None,
            headers='{"host": "example.com", "x-evil": "<script>"}',
            body=memoryview(b"\xff" * 2000),
            body_size=2000,
        )
    )
    assert detail.headers == {"host": "example.com", "x-evil": "<script>"}
    assert detail.body == decode_body(b"\xff" * 2000)
    assert (detail.body_size, detail.body_truncated) == (2000, False)


def test_a_login_attempt_keeps_the_credentials_in_full():
    event = login_attempt_event(
        queries.GetLoginAttemptsByIdsRow(
            id_=2,
            ip_address=IP,
            attempted_at=AT,
            endpoint_path=PATH,
            username=USERNAME,
            password=PASSWORD,
            was_fake_success=True,
        )
    )
    assert event == LoginAttemptEvent(
        kind=EventKind.LOGIN_ATTEMPT,
        id=2,
        occurred_at=AT,
        ip_address=IP,
        path=PATH,
        username=USERNAME,
        password=PASSWORD,
        decoy_accepted=True,
    )


def test_decoy_events_map_their_decoy():
    view = decoy_view_event(
        queries.GetDecoyViewsByIdsRow(
            id_=3,
            ip_address=IP,
            viewed_at=AT,
            decoy_slug=DOWNLOAD,
            decoy_type=enums.DecoyType.BINARY,
        )
    )
    assert view == DecoyViewEvent(
        kind=EventKind.DECOY_VIEW,
        id=3,
        occurred_at=AT,
        ip_address=IP,
        decoy_slug=DOWNLOAD,
        decoy_type=enums.DecoyType.BINARY,
    )
    attempt = decoy_password_attempt_event(
        queries.GetDecoyPasswordAttemptsByIdsRow(
            id_=4,
            ip_address=IP,
            attempted_at=AT,
            decoy_slug=NOTE,
            successful=False,
        )
    )
    assert attempt == DecoyPasswordAttemptEvent(
        kind=EventKind.DECOY_PASSWORD_ATTEMPT,
        id=4,
        occurred_at=AT,
        ip_address=IP,
        decoy_slug=NOTE,
        decoy_accepted=False,
    )


def test_events_keep_the_page_order_when_kinds_interleave():
    # Ids repeat across kinds: an event is its kind and id together.
    order = [
        (EventKind.HIT, 1),
        (EventKind.LOGIN_ATTEMPT, 1),
        (EventKind.HIT, 2),
        (EventKind.LOGIN_ATTEMPT, 2),
    ]
    page = [
        models.VisitorEvent(kind=kind, id_=id_, ip_address=IP, occurred_at=AT)
        for kind, id_ in order
    ]
    hits = [hit_event(hit_row(b"", None).model_copy(update={"id_": n})) for n in (2, 1)]
    logins = [
        LoginAttemptEvent(
            kind=EventKind.LOGIN_ATTEMPT,
            id=n,
            occurred_at=AT,
            ip_address=IP,
            path=PATH,
            username="u",
            password="p",
            decoy_accepted=False,
        )
        for n in (2, 1)
    ]
    # Fetched per kind, in no particular order; one hit was deleted in between.
    events = in_page_order(page, [*logins, *hits[1:]])
    assert [(event.kind, event.id) for event in events] == [
        key for key in order if key != (EventKind.HIT, 2)
    ]


def test_an_address_with_no_requests_has_an_empty_summary():
    summary = ip_summary(None)
    assert (summary.requests, summary.first_seen_at) == (0, None)


def test_every_event_kind_is_required_in_the_schema():
    # With a default, `kind` would be optional in the generated TypeScript, which then couldn't
    # narrow the event union on it.
    for model in (
        HitEvent,
        LoginAttemptEvent,
        DecoyViewEvent,
        DecoyPasswordAttemptEvent,
    ):
        assert (
            DISCRIMINATOR in model.model_json_schema(mode="serialization")["required"]
        )
