from datetime import UTC, datetime
from http import HTTPMethod

import pytest
from psycopg import AsyncConnection

from attenborough import events
from attenborough.db import queries
from attenborough.db.enums import EventKind, PathCategory, RouterGroup
from attenborough.events import (
    DISCRIMINATOR,
    HONEYPOT_PLACEHOLDER,
    CanaryOrigin,
    HitEvent,
    InstallAttemptEvent,
    InstallOrigin,
    LoginAttemptEvent,
    decode_body,
    hit_detail,
    hit_event,
    honeypot_pattern,
    in_page_order,
    install_attempt_event,
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
CANARY_PATH = "/.env"
CANARY_IP = "198.51.100.4"
INSTALL_PATH = "/wp-admin/install.php"
INSTALL_IP = "192.0.2.9"
EMAIL = "owner@example.net"


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
        category=PathCategory.WORDPRESS,
        banned=False,
        custom_response=False,
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
        category=PathCategory.WORDPRESS,
        banned=False,
        custom_response=False,
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
            category=PathCategory.WORDPRESS,
            banned=False,
            custom_response=False,
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
            canary_path=None,
            canary_ip_address=None,
            canary_issued_at=None,
            install_id=None,
            install_ip_address=None,
            install_attempted_at=None,
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
        canary=None,
        install=None,
    )


def test_a_canary_password_says_where_it_was_handed_out():
    event = login_attempt_event(
        queries.GetLoginAttemptsByIdsRow(
            id_=3,
            ip_address=IP,
            attempted_at=AT,
            endpoint_path=PATH,
            username=USERNAME,
            password=PASSWORD,
            was_fake_success=False,
            canary_path=CANARY_PATH,
            canary_ip_address=CANARY_IP,
            canary_issued_at=AT,
            install_id=None,
            install_ip_address=None,
            install_attempted_at=None,
        )
    )
    assert event.canary == CanaryOrigin(
        path=CANARY_PATH, ip_address=CANARY_IP, issued_at=AT
    )


def test_a_login_with_an_installed_account_says_which_install_created_it():
    event = login_attempt_event(
        queries.GetLoginAttemptsByIdsRow(
            id_=4,
            ip_address=IP,
            attempted_at=AT,
            endpoint_path=PATH,
            username=USERNAME,
            password=PASSWORD,
            was_fake_success=False,
            canary_path=None,
            canary_ip_address=None,
            canary_issued_at=None,
            install_id=9,
            install_ip_address=INSTALL_IP,
            install_attempted_at=AT,
        )
    )
    assert event.install == InstallOrigin(id=9, ip_address=INSTALL_IP, attempted_at=AT)


def test_an_install_keeps_the_chosen_account_in_full():
    event = install_attempt_event(
        queries.GetInstallAttemptsByIdsRow(
            id_=5,
            ip_address=IP,
            attempted_at=AT,
            path=INSTALL_PATH,
            site_title=PASSWORD,
            username=USERNAME,
            email=EMAIL,
            password=PASSWORD,
            password_generated=True,
        )
    )
    assert event == InstallAttemptEvent(
        kind=EventKind.INSTALL_ATTEMPT,
        id=5,
        occurred_at=AT,
        ip_address=IP,
        path=INSTALL_PATH,
        site_title=PASSWORD,
        username=USERNAME,
        email=EMAIL,
        password=PASSWORD,
        password_generated=True,
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
        queries.ListRecentEventsRow(kind=kind, id_=id_, ip_address=IP, occurred_at=AT)
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
            canary=None,
            install=None,
        )
        for n in (2, 1)
    ]
    # Fetched per kind, in no particular order; one hit was deleted in between.
    events = in_page_order(page, [*logins, *hits[1:]])
    assert [(event.kind, event.id) for event in events] == [
        key for key in order if key != (EventKind.HIT, 2)
    ]


def test_an_address_with_no_activity_has_an_empty_summary():
    summary = ip_summary(None, None, None)
    assert (summary.requests, summary.first_seen_at, summary.ban) == (0, None, None)


def test_a_ban_shows_only_its_dates():
    ban = queries.GetActiveIpBanRow(added=AT, expires=None)
    summary = ip_summary(None, None, ban)
    assert summary.ban is not None
    assert summary.ban.model_dump() == {"since": AT, "until": None}


HIDDEN_NAME = "secret.example.org"
HIDDEN_IP = "203.0.113.5"
HIDDEN = honeypot_pattern([HIDDEN_NAME, HIDDEN_IP])


@pytest.mark.parametrize(
    "text, shown",
    [
        (HIDDEN_NAME, HONEYPOT_PLACEHOLDER),
        (f"{HIDDEN_NAME.upper()}:443", f"{HONEYPOT_PLACEHOLDER}:443"),
        (f"www.{HIDDEN_NAME}", f"www.{HONEYPOT_PLACEHOLDER}"),
        # WordPress's form posts its own URL, encoded.
        (
            f"redirect_to=https%3A%2F%2F{HIDDEN_NAME}%2Fwp-admin%2F",
            f"redirect_to=https%3A%2F%2F{HONEYPOT_PLACEHOLDER}%2Fwp-admin%2F",
        ),
        (
            f"GET http://{HIDDEN_IP}/ HTTP/1.1",
            f"GET http://{HONEYPOT_PLACEHOLDER}/ HTTP/1.1",
        ),
    ],
)
def test_the_honeypots_own_names_are_hidden(text: str, shown: str):
    assert HIDDEN.sub(HONEYPOT_PLACEHOLDER, text) == shown


# Other addresses that merely contain them stay as sent.
@pytest.mark.parametrize("text", [f"{HIDDEN_IP}0", f"1{HIDDEN_IP}", "example.org"])
def test_other_names_are_shown_as_sent(text: str):
    assert HIDDEN.sub(HONEYPOT_PLACEHOLDER, text) == text


def test_every_text_a_visitor_sent_is_hidden_in(monkeypatch: pytest.MonkeyPatch):
    host = "honeypot.test"
    monkeypatch.setattr(events, "HONEYPOT", honeypot_pattern([host]))
    hidden = events.hit_detail(
        queries.GetHitRow(
            id_=1,
            ip_address=IP,
            occurred_at=AT,
            method=HTTPMethod.GET,
            path=f"/{host}",
            query=host,
            status_code=200,
            user_agent=host,
            headers=f'{{"host": "{host}", "{host}": "x"}}',
            body=memoryview(host.encode()),
            body_size=len(host),
            category=PathCategory.OTHER,
            banned=False,
            custom_response=False,
        )
    )
    assert host not in hidden.model_dump_json()


def test_every_event_kind_is_required_in_the_schema():
    # With a default, `kind` would be optional in the generated TypeScript, which then couldn't
    # narrow the event union on it.
    for model in (
        HitEvent,
        LoginAttemptEvent,
        InstallAttemptEvent,
    ):
        assert (
            DISCRIMINATOR in model.model_json_schema(mode="serialization")["required"]
        )


@pytest.mark.anyio
async def test_a_takeover_is_its_install_and_the_logins_into_its_account_in_order(
    db_conn: AsyncConnection,
):
    username = "test-takeover-admin"
    other_ip = "203.0.113.8"

    async def log_in(ip: str, password: str) -> None:
        _ = await queries.create_credential_stuffing_attempt(
            db_conn,
            ip_address=ip,
            endpoint_path=PATH,
            username=username,
            password=password,
            checked=True,
            author_password=False,
        )

    async with db_conn.transaction(force_rollback=True):
        install_id = await queries.create_install_attempt(
            db_conn,
            ip_address=IP,
            path="/wp-admin/install.php",
            site_title="",
            username=username,
            email="takeover@example.net",
            password=PASSWORD,
            password_generated=False,
        )
        assert install_id is not None
        for ip in (IP, other_ip, other_ip):
            await log_in(ip, PASSWORD)
        # Any other password opens nothing, so it isn't part of the takeover.
        await log_in(IP, "wrong")
        takeover = await events.fetch_takeover(db_conn, install_id)
        missing = await events.fetch_takeover(db_conn, install_id + 1)

    assert takeover is not None
    assert takeover.install.id == install_id
    assert takeover.login_count == 3
    assert [login.ip_address for login in takeover.logins] == [IP, other_ip, other_ip]
    assert all(login.decoy_accepted for login in takeover.logins)
    assert missing is None


@pytest.mark.anyio
async def test_the_exhibit_shows_nothing_of_private_addresses(db_conn: AsyncConnection):
    private_ip, public_ip = "192.168.20.1", "203.0.113.200"
    cursor = events.FIRST_PAGE

    async def visit(ip: str) -> None:
        await queries.create_telemetry_hit(
            db_conn,
            ip_address=ip,
            method=HTTPMethod.GET,
            path=PATH,
            query=None,
            router_group=RouterGroup.HONEYPOT,
            user_agent=USER_AGENT,
            headers="{}",
            body=None,
            body_size=None,
            status_code=200,
            banned=False,
            rule_id=None,
        )

    async def listed(ip: str) -> int:
        rows = await queries.list_ip_events(
            db_conn,
            ip_address=ip,
            before_at=cursor.occurred_at,
            before_kind=cursor.kind,
            before_id=cursor.id,
            limit=1,
        )
        return len(rows)

    async def addresses() -> int:
        totals = await queries.get_pattern_totals(db_conn)
        assert totals is not None
        return totals.addresses

    async with db_conn.transaction(force_rollback=True):
        before = await addresses()
        await visit(private_ip)
        await visit(public_ip)
        assert await listed(private_ip) == 0
        assert await queries.get_ip_activity(db_conn, ip_address=private_ip) is None
        assert await listed(public_ip) == 1
        assert await queries.get_ip_activity(db_conn, ip_address=public_ip) is not None
        assert await addresses() == before + 1
