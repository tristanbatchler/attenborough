from datetime import UTC, datetime
from http import HTTPMethod

import pytest
from pydantic import ValidationError

from attenborough.db import queries
from attenborough.rules import (
    MARKERS,
    Marker,
    Request,
    RuleForm,
    context,
    sample_context,
)

IP = "198.51.100.23"
AT = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
EVIL_AGENT = 'zgrab <script>"x"</script>'
JSON = "application/json"
TEXT = "text/plain"
FACTS = queries.GetVisitorFactsRow(
    country_code="RU",
    city="Moscow",
    asn=14061,
    as_organisation="DIGITALOCEAN-ASN",
    requests=4312,
    first_seen_at=AT,
    logins=25,
    has_canary=False,
    banned_before=True,
)


def markers(
    method: str = HTTPMethod.GET, path: str = "/", user_agent: str = EVIL_AGENT
) -> dict[str, object]:
    request = Request(
        method=method, path=path, query=None, headers={"user-agent": user_agent}
    )
    return context(IP, FACTS, request, AT)


@pytest.mark.parametrize(
    "method, pattern, request_method, path, expected",
    [
        (None, None, HTTPMethod.POST, "/anything", True),
        (HTTPMethod.POST, None, HTTPMethod.GET, "/", False),
        (None, "/xmlrpc.php", HTTPMethod.POST, "/xmlrpc.php", True),
        (None, "*.env", HTTPMethod.GET, "/api/.env", True),
        (None, "/wp-content/*", HTTPMethod.GET, "/wp-admin/", False),
    ],
)
def test_a_rule_matches_by_method_and_path(
    method: str | None,
    pattern: str | None,
    request_method: str,
    path: str,
    expected: bool,
):
    rule = RuleForm(method=method, path_pattern=pattern).rule()
    assert rule.matches_request(request_method, path) is expected


@pytest.mark.parametrize(
    "condition, expected",
    [
        ("", True),
        ('country == "RU"', True),
        ('(country == "RU" or asn == 14061) and logins_10m >= 20', True),
        ("not banned_before", False),
        ('user_agent contains "zgrab"', True),
        ("requests < 100", False),
    ],
)
def test_a_condition_reads_the_markers(condition: str, expected: bool):
    assert RuleForm(condition=condition).rule().holds(markers()) is expected


def test_html_bodies_escape_what_the_visitor_sent():
    rule = RuleForm(body="<p>{{ ip }} says {{ user_agent }}</p>").rule()
    body = rule.render(markers()).body
    assert body.startswith(f"<p>{IP} says zgrab &lt;script&gt;")
    assert "<script>" not in body


def test_json_bodies_quote_with_the_json_filter():
    rule = RuleForm(content_type=JSON, body='{"agent": {{ user_agent | json }}}').rule()
    assert rule.render(markers()).body == '{"agent": "zgrab <script>\\"x\\"</script>"}'


def test_loops_and_dates_work():
    rule = RuleForm(
        content_type=TEXT,
        body='{% for i in (1..3) %}{{ i }}{% endfor %} since {{ first_seen | date: "%Y-%m-%d" }}',
    ).rule()
    assert rule.render(markers()).body == "123 since 2026-10-03"


def test_header_values_are_templates_and_never_break_the_header():
    rule = RuleForm(headers={"Location": "/{{ user_agent }}"}).rule()
    location = rule.render(markers(user_agent="a\r\nSet-Cookie: x=1")).headers[
        "Location"
    ]
    assert location == "/aSet-Cookie: x=1"


def test_only_a_rule_that_uses_the_canary_issues_one():
    assert RuleForm(body="DB_PASSWORD={{ canary }}").rule().uses_canary()
    assert not RuleForm(body="{{ ip }}").rule().uses_canary()
    with_canary = {**sample_context(), Marker.CANARY: "s3cret"}
    assert RuleForm(body="{{ canary }}").rule().render(with_canary).body == "s3cret"


@pytest.mark.parametrize(
    "form",
    [
        # Liquid syntax errors.
        {"condition": 'country == "RU" and'},
        {"body": "{% if %}"},
        # A marker that doesn't exist: a typo would otherwise never match.
        {"condition": 'contry == "RU"'},
        {"body": "{{ visitor_ip }}"},
        # Limits: a runaway loop, and output over 64 KiB.
        {"body": "{% for i in (1..1000000) %}x{% endfor %}"},
        {"body": '{{ "x" | append: "" }}' + "y" * 70_000},
        # Headers the server owns, or that aren't headers.
        {"headers": {"Content-Length": "1"}},
        {"headers": {"Bad Name": "x"}},
        # A body where none is allowed.
        {"status_code": 204, "body": "x"},
        {"status_code": 101},
    ],
)
def test_a_rule_that_cannot_render_is_refused_on_save(form: dict[str, object]):
    with pytest.raises(ValidationError):
        _ = RuleForm.model_validate(form)


def test_a_rule_is_normalised_on_save():
    form = RuleForm(method=" post ", path_pattern="  ")
    assert (form.method, form.path_pattern) == (HTTPMethod.POST, None)


def test_the_markers_listed_are_the_markers_given():
    assert set(sample_context()) == set(MARKERS)
    assert set(markers()) == set(MARKERS) - {Marker.CANARY}
