from datetime import datetime, timezone

from standup_aggregator.discover import MeetingSummary, in_window

UTC = timezone.utc


def _m(name: str, created: str) -> MeetingSummary:
    return MeetingSummary(
        id=name,
        name=name,
        team_id="t1",
        team_name="Team",
        created_at=datetime.fromisoformat(created.replace("Z", "+00:00")),
        ended_at=None,
        response_count=0,
    )


def test_in_window_includes_meetings_inside_range():
    since = datetime(2026, 5, 1, tzinfo=UTC)
    until = datetime(2026, 5, 7, 23, 59, tzinfo=UTC)
    m = _m("a", "2026-05-03T12:00:00Z")
    assert in_window(m, since, until) is True


def test_in_window_excludes_meeting_before_since():
    since = datetime(2026, 5, 1, tzinfo=UTC)
    until = datetime(2026, 5, 7, tzinfo=UTC)
    m = _m("old", "2026-04-30T23:59:59Z")
    assert in_window(m, since, until) is False


def test_in_window_excludes_meeting_after_until():
    since = datetime(2026, 5, 1, tzinfo=UTC)
    until = datetime(2026, 5, 7, tzinfo=UTC)
    m = _m("future", "2026-05-08T00:00:00Z")
    assert in_window(m, since, until) is False


def test_in_window_inclusive_at_boundaries():
    since = datetime(2026, 5, 1, tzinfo=UTC)
    until = datetime(2026, 5, 7, tzinfo=UTC)
    assert in_window(_m("at_since", "2026-05-01T00:00:00Z"), since, until) is True
    assert in_window(_m("at_until", "2026-05-07T00:00:00Z"), since, until) is True
