from datetime import UTC, date, datetime, timedelta

import pytest
from psycopg import AsyncConnection

from attenborough.db import queries
from attenborough.patterns import (
    HOURS_PER_DAY,
    REFRESH_INTERVAL,
    WINDOW_DAYS,
    LatestPatterns,
    Patterns,
    day_activity,
    window_days,
)

TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def test_the_window_is_whole_days_ending_today():
    days = window_days(TODAY)
    assert len(days) == WINDOW_DAYS
    assert days[-1] == TODAY
    assert days == sorted(days)


def test_each_day_has_every_hour_with_zeros_where_nothing_came():
    days = window_days(TODAY)
    rows = [
        queries.CountRequestsPerHourSinceRow(
            hour=datetime(2026, 10, 3, 4, tzinfo=UTC), requests=327
        ),
        queries.CountRequestsPerHourSinceRow(
            hour=datetime(2026, 10, 3, 23, tzinfo=UTC), requests=1
        ),
    ]
    activity = day_activity(days, rows)
    assert [day.day for day in activity] == days
    assert all(len(day.requests_by_hour) == HOURS_PER_DAY for day in activity)
    today = activity[-1].requests_by_hour
    assert (today[4], today[23], sum(today)) == (327, 1, 328)
    assert sum(sum(day.requests_by_hour) for day in activity[:-1]) == 0


@pytest.mark.anyio
async def test_the_figures_are_recomputed_only_after_the_refresh_interval(
    db_conn: AsyncConnection,
):
    computed: list[datetime] = []

    async def compute(_: AsyncConnection, now: datetime) -> Patterns:
        computed.append(now)
        return Patterns.model_construct(computed_at=now)

    latest = LatestPatterns(compute)
    first = await latest.get(db_conn, NOW)
    assert (
        await latest.get(db_conn, NOW + REFRESH_INTERVAL - timedelta(seconds=1))
        is first
    )
    assert await latest.get(db_conn, NOW + REFRESH_INTERVAL) is not first
    assert computed == [NOW, NOW + REFRESH_INTERVAL]
