from datetime import UTC, datetime
from http import HTTPMethod

import pytest
from psycopg import AsyncConnection

from attenborough import events
from attenborough.db import queries
from attenborough.db.enums import EventKind, PathCategory, RouterGroup
from attenborough.events import HONEYPOT_PLACEHOLDER, honeypot_pattern
from attenborough.search import FIELDS, Search, SearchError, SearchField

DAY = datetime(2026, 9, 1, tzinfo=UTC)
NEXT_DAY = datetime(2026, 9, 2, tzinfo=UTC)


def test_every_field_is_described():
    assert set(FIELDS) == set(SearchField)


def test_terms_values_and_negation():
    search = Search.parse(
        'country:ru, CN -path:/wp-* user_agent:"Mozilla (KHTML, like Gecko)" kind:hit'
    )
    assert search.countries.include == ["RU", "CN"]
    assert search.paths.exclude == ["/wp-%"]
    assert search.user_agents.include == ["Mozilla (KHTML, like Gecko)"]
    assert search.kinds.include == [EventKind.HIT]
    assert search.fields == {
        SearchField.COUNTRY,
        SearchField.PATH,
        SearchField.USER_AGENT,
        SearchField.KIND,
    }


def test_repeating_a_field_adds_values():
    assert Search.parse("status:404 status:403,500").statuses.include == [404, 403, 500]


def test_globs_become_like_patterns_that_match_like_and_escapes_literally():
    assert Search.parse(r'path:"/50%_off\*?"').paths.include == [r"/50\%\_off\\%_"]


def test_a_bare_address_or_network_means_ip():
    search = Search.parse("203.0.113.7 -198.51.100.0/24 2001:db8::1")
    assert search.ips.include == ["203.0.113.7/32", "2001:db8::1/128"]
    assert search.ips.exclude == ["198.51.100.0/24"]


@pytest.mark.parametrize(
    "value, start, stop",
    [
        ("10", 10, 11),
        (">10", 11, None),
        (">=10", 10, None),
        ("<10", None, 10),
        ("<=10", None, 11),
        ("10..20", 10, 21),
    ],
)
def test_count_ranges_are_half_open(value: str, start: int | None, stop: int | None):
    requests = Search.parse(f"requests:{value}").requests
    assert (requests.start, requests.stop) == (start, stop)


def test_a_day_is_the_whole_day_and_a_minute_one_minute():
    assert (
        Search.parse("date:2026-09-01").date.start,
        Search.parse("date:2026-09-01").date.stop,
    ) == (DAY, NEXT_DAY)
    minute = Search.parse("date:<=2026-09-01T00:00").date
    assert (minute.start, minute.stop) == (None, datetime(2026, 9, 1, 0, 1, tzinfo=UTC))


def test_ranges_narrow():
    date = Search.parse(
        "date:>=2026-08-01 date:<2026-09-02 date:2026-09-01..2026-09-30"
    ).date
    assert (date.start, date.stop) == (DAY, NEXT_DAY)


@pytest.mark.parametrize(
    "query, hits, logins, installs",
    [
        ("", True, True, True),
        ("kind:hit,login_attempt", True, True, False),
        ("-kind:hit", False, True, True),
        ("status:404", True, False, False),
        ("username:admin", False, True, True),
        ("path:/wp-login.php", True, True, True),
        ("status:404 username:admin", False, False, False),
    ],
)
def test_fields_only_some_kinds_have_leave_the_others_out(
    query: str, hits: bool, logins: bool, installs: bool
):
    search = Search.parse(query)
    assert search.includes(EventKind.HIT) is hits
    assert search.includes(EventKind.LOGIN_ATTEMPT) is logins
    assert search.includes(EventKind.INSTALL_ATTEMPT) is installs


@pytest.mark.parametrize(
    "query",
    [
        "foo",
        "nope:1",
        "country:USA",
        "requests:-1",
        "-date:>2026-09-01",
        "requests:1,2",
        'ip:"203.0.113.7',
        "ip:nowhere",
        "status:4xx",
        "date:2026-13-01",
        "kind:everything",
        "banned:maybe",
        "banned:true -banned:true",
    ],
)
def test_queries_that_cant_be_searched_say_why(query: str):
    with pytest.raises(SearchError):
        _ = Search.parse(query)


def test_the_category_names_are_the_enums():
    assert Search.parse("category:Secrets").categories.include == [PathCategory.SECRETS]


@pytest.mark.anyio
async def test_a_search_matches_text_as_the_exhibit_shows_it(
    db_conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
):
    host = "honeypot.test"
    monkeypatch.setattr(events, "HONEYPOT", honeypot_pattern([host]))
    ip, private_ip = "192.0.2.231", "10.9.8.7"

    async def visit(address: str, user_agent: str) -> None:
        await queries.create_telemetry_hit(
            db_conn,
            ip_address=address,
            method=HTTPMethod.GET,
            path="/.env",
            query=None,
            router_group=RouterGroup.HONEYPOT,
            user_agent=user_agent,
            headers="{}",
            body=None,
            body_size=None,
            status_code=404,
            banned=False,
            rule_id=None,
        )

    async def found(query: str) -> list[EventKind]:
        rows = await Search.parse(query).run(db_conn, events.FIRST_PAGE, 10)
        return [row.kind for row in rows]

    async with db_conn.transaction(force_rollback=True):
        await visit(ip, f"scanner for {host}")
        await visit(private_ip, "scanner")
        _ = await queries.create_credential_stuffing_attempt(
            db_conn,
            ip_address=ip,
            endpoint_path="/wp-login.php",
            username="admin",
            password="hunter2",
            checked=False,
            author_password=False,
        )
        hit, login = [EventKind.HIT], [EventKind.LOGIN_ATTEMPT]
        assert await found(f"ip:{ip}") == [EventKind.LOGIN_ATTEMPT, EventKind.HIT]
        # Matching the stored text would confirm a guess at the honeypot's name.
        assert await found(f"ip:{ip} user_agent:*{host}*") == []
        assert await found(f"ip:{ip} user_agent:*{HONEYPOT_PLACEHOLDER}*") == hit
        assert await found(f"ip:{ip} category:secrets -status:200") == hit
        assert await found(f"ip:{ip} username:ADM* -password:*1*") == login
        assert await found(f"ip:{ip} requests:1 logins:>=1") == [*login, *hit]
        assert await found(f"ip:{ip} requests:>1") == []
        assert await found(f"{private_ip}") == []
