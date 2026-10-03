import base64
from collections.abc import Callable

import pytest
from psycopg import AsyncConnection
from pydantic import BaseModel, ValidationError

from attenborough.db import queries
from attenborough.ingest import (
    TARPIT_FREE_ATTEMPTS,
    TARPIT_MAX_DELAY_MS,
    TARPIT_STEP_MS,
    DecoyHit,
    InstallAttempt,
    LoginAttempt,
    account_password,
    tarpit_delay_ms,
)

# The parametrized argument: a function building one report.
REPORT = "report"
CHOSEN = "chosen"
LOGIN_PATH = "/wp-login.php"
INSTALL_PATH = "/wp-admin/install.php"
# Any character, repeated past a limit.
FILLER = "x"
TOO_LONG = FILLER * (16 * 1024 + 1)
TOO_MANY_HEADERS = {str(i): "" for i in range(2001)}
# Bodies travel as base64.
TOO_BIG_BODY = base64.b64encode(bytes(1024 * 1024 + 1)).decode()
# Credentials are parsed from a body, so they share its limit.
TOO_LONG_CREDENTIAL = FILLER * (1024 * 1024 + 1)
# An address from TEST-NET-1 (RFC 5737), never a real visitor.
TEST_IP = "192.0.2.1"


def hit(
    *,
    method: str = "GET",
    path: str = LOGIN_PATH,
    query: str | None = None,
    headers: dict[str, str] | None = None,
    body: str = "",
    status_code: int = 200,
) -> DecoyHit:
    return DecoyHit.model_validate(
        {
            "method": method,
            "path": path,
            "query": query,
            "headers": headers or {},
            "body": body,
            "status_code": status_code,
        }
    )


def login(
    *, path: str = LOGIN_PATH, username: str = "", password: str = ""
) -> LoginAttempt:
    return LoginAttempt(path=path, username=username, password=password)


def install(
    *,
    path: str = INSTALL_PATH,
    site_title: str = "",
    username: str = "admin",
    email: str = "owner@example.net",
    password: str = "",
) -> InstallAttempt:
    return InstallAttempt(
        path=path,
        site_title=site_title,
        username=username,
        email=email,
        password=password,
    )


@pytest.mark.parametrize(REPORT, [hit, login, install])
def test_ingest_accepts_valid_reports(report: Callable[[], BaseModel]):
    _ = report()


# Everything the decoy app reports is attacker-controlled, so every field is bounded.
@pytest.mark.parametrize(
    REPORT,
    [
        lambda: hit(path=TOO_LONG),
        lambda: hit(query=TOO_LONG),
        lambda: hit(body=TOO_BIG_BODY),
        lambda: hit(method=""),
        lambda: hit(status_code=99),
        lambda: hit(status_code=600),
        lambda: hit(headers=TOO_MANY_HEADERS),
        lambda: login(path=TOO_LONG),
        lambda: login(username=TOO_LONG_CREDENTIAL),
        lambda: login(password=TOO_LONG_CREDENTIAL),
        lambda: install(path=TOO_LONG),
        lambda: install(site_title=TOO_LONG_CREDENTIAL),
        lambda: install(username=TOO_LONG_CREDENTIAL),
        lambda: install(email=TOO_LONG_CREDENTIAL),
        lambda: install(password=TOO_LONG_CREDENTIAL),
    ],
)
def test_ingest_rejects_out_of_bounds_reports(report: Callable[[], BaseModel]):
    with pytest.raises(ValidationError):
        _ = report()


def test_the_tarpit_lets_the_first_attempts_through_then_slows_down_to_a_cap():
    assert tarpit_delay_ms(0) == 0
    assert tarpit_delay_ms(TARPIT_FREE_ATTEMPTS - 1) == 0
    assert tarpit_delay_ms(TARPIT_FREE_ATTEMPTS) == TARPIT_STEP_MS
    assert tarpit_delay_ms(TARPIT_FREE_ATTEMPTS + 1) == 2 * TARPIT_STEP_MS
    assert tarpit_delay_ms(1_000_000) == TARPIT_MAX_DELAY_MS


def test_an_installed_account_keeps_its_chosen_password_trimmed_as_wordpress_stores_it():
    assert account_password(" hunter2\t\n") == ("hunter2", False)


@pytest.mark.parametrize(CHOSEN, ["", " \t\r\n\0\x0b"])
def test_an_install_without_a_password_gets_a_made_up_one_like_wordpress_gives(
    chosen: str,
):
    password, generated = account_password(chosen)
    assert generated
    assert len(password) == 12
    assert password.isascii()
    assert password.isalnum()
    assert account_password(chosen)[0] != password


@pytest.mark.anyio
async def test_only_an_installed_account_with_its_own_password_opens(
    db_conn: AsyncConnection,
):
    username, email, password = "test-installed-admin", "test@example.net", "chosen"

    async def outcome(login: str, tried: str) -> tuple[bool, bool]:
        recorded = await queries.create_credential_stuffing_attempt(
            db_conn,
            ip_address=TEST_IP,
            endpoint_path=LOGIN_PATH,
            username=login,
            password=tried,
        )
        assert recorded is not None
        return recorded.was_fake_success, recorded.known_account

    async with db_conn.transaction(force_rollback=True):
        assert await outcome(username, password) == (False, False)
        await queries.create_install_attempt(
            db_conn,
            ip_address=TEST_IP,
            path=INSTALL_PATH,
            site_title="",
            username=username,
            email=email,
            password=password,
            password_generated=False,
        )
        assert await outcome(username, password) == (True, True)
        assert await outcome(email, password) == (True, True)
        assert await outcome(username, "wrong") == (False, True)
        assert await outcome("test-someone-else", password) == (False, False)
