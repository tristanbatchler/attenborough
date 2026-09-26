import base64
from collections.abc import Callable

import pytest
from pydantic import BaseModel, ValidationError

from attenborough.ingest.models import DecoyHit, LoginAttempt

# The parametrized argument: a function building one report.
REPORT = "report"
LOGIN_PATH = "/wp-login.php"
# Any character, repeated past a limit.
FILLER = "x"
TOO_LONG = FILLER * (16 * 1024 + 1)
TOO_MANY_HEADERS = {str(i): "" for i in range(2001)}
# Bodies travel as base64.
TOO_BIG_BODY = base64.b64encode(bytes(1024 * 1024 + 1)).decode()
# Credentials are parsed from a body, so they share its limit.
TOO_LONG_CREDENTIAL = FILLER * (1024 * 1024 + 1)


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


@pytest.mark.parametrize(REPORT, [hit, login])
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
    ],
)
def test_ingest_rejects_out_of_bounds_reports(report: Callable[[], BaseModel]):
    with pytest.raises(ValidationError):
        _ = report()
