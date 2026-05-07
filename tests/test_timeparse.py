from datetime import datetime, timedelta, timezone

import pytest

from standup_aggregator.timeparse import (
    DEFAULT_WINDOW_DESCRIPTION,
    TimeParseError,
    parse_window,
    parse_when,
)

UTC = timezone.utc


def test_parse_when_iso_date_returns_midnight_utc():
    got = parse_when("2026-05-01", now=datetime(2026, 5, 7, 12, 0, tzinfo=UTC))
    assert got == datetime(2026, 5, 1, 0, 0, tzinfo=UTC)


def test_parse_when_iso_datetime_with_z_returns_aware_utc():
    got = parse_when("2026-05-01T13:30:00Z", now=datetime(2026, 5, 7, 12, 0, tzinfo=UTC))
    assert got == datetime(2026, 5, 1, 13, 30, tzinfo=UTC)


def test_parse_when_today_is_midnight_utc_of_now_date():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    got = parse_when("today", now=now)
    assert got == datetime(2026, 5, 7, 0, 0, tzinfo=UTC)


def test_parse_when_yesterday_is_midnight_utc_of_day_before():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    got = parse_when("yesterday", now=now)
    assert got == datetime(2026, 5, 6, 0, 0, tzinfo=UTC)


def test_parse_when_relative_days_subtracts_from_now():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    got = parse_when("7d", now=now)
    assert got == now - timedelta(days=7)


def test_parse_when_relative_weeks_subtracts_from_now():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    got = parse_when("2w", now=now)
    assert got == now - timedelta(weeks=2)


def test_parse_when_rejects_garbage():
    with pytest.raises(TimeParseError):
        parse_when("not a date", now=datetime(2026, 5, 7, tzinfo=UTC))


def test_parse_window_default_is_today_utc_to_now():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    since, until, desc = parse_window(None, None, now=now)
    assert since == datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    assert until == now
    assert desc == DEFAULT_WINDOW_DESCRIPTION


def test_parse_window_uses_explicit_values():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    since, until, _ = parse_window("2026-05-01", "2026-05-07", now=now)
    assert since == datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    assert until == datetime(2026, 5, 7, 0, 0, tzinfo=UTC)


def test_parse_window_until_only_uses_default_since():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    since, until, _ = parse_window(None, "2026-05-07T18:00:00Z", now=now)
    assert since == datetime(2026, 5, 7, 0, 0, tzinfo=UTC)
    assert until == datetime(2026, 5, 7, 18, 0, tzinfo=UTC)


def test_parse_window_rejects_inverted_range():
    now = datetime(2026, 5, 7, 14, 30, tzinfo=UTC)
    with pytest.raises(TimeParseError):
        parse_window("2026-05-07", "2026-05-01", now=now)
