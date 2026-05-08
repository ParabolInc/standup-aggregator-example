"""Discover TeamPromptMeetings (Stand-Ups) inside a date window.

Strategy (confirmed by introspection against live API):

  The Parabol schema does NOT have a per-team paginated meetings field.
  Instead, the viewer-level User.meetings field accepts:

    meetings(first, teamIds, meetingTypes, after, before)

  where `before` is a required DateTime, `after` is an optional DateTime
  lower-bound date filter, and both `teamIds` and `meetingTypes` are
  required non-null lists.

  DateTime scalars MUST include milliseconds in the format:
  YYYY-MM-DDTHH:MM:SS.SSSZ — the server rejects ISO strings without ms.

  Pagination advances the UPPER bound (`before`), not `after`.
  Parabol returns results newest-first; `after` acts as a fixed
  lower-bound date filter (not a forward-paging cursor). Setting
  after=endCursor on the next call would return the same meetings
  inclusively, doubling every row. Instead, on each subsequent page
  `before` is advanced to the createdAt of the oldest meeting seen on
  the previous page, asking the API for strictly older meetings. `after`
  stays pinned at the user's --since for every call. A seen_ids set
  defensively dedups in case the API ever returns boundary rows twice.
  Stop when hasNextPage is false, no new ids are found, or the new
  `before` would equal the previous one (no progress).

  Discovery flow:
  1. Query VIEWER_QUERY for the list of teams visible to the PAT.
  2. Optionally filter to --team flags (by id or display name).
  3. Pass all surviving team IDs to TEAM_MEETINGS_QUERY in one request,
     paginating until hasNextPage is false. The API server-side filters
     to the requested teams, so no client-side grouping by teamId is
     needed — but we do need a lookup map to resolve team names.
  4. Filter each page's meetings client-side to the [since, until]
     window (inclusive on both ends).

  The pure helpers (MeetingSummary, in_window, filter_teams) are
  covered by unit tests in tests/test_discover.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from standup_aggregator.client import ParabolClient
from standup_aggregator.queries import TEAM_MEETINGS_QUERY, VIEWER_QUERY


@dataclass(frozen=True, slots=True)
class MeetingSummary:
    """Lightweight meeting record returned by discovery."""

    id: str
    name: str
    team_id: str
    team_name: str
    created_at: datetime
    ended_at: datetime | None
    response_count: int


def in_window(meeting: MeetingSummary, since: datetime, until: datetime) -> bool:
    """Inclusive check on createdAt against a [since, until] range."""
    return since <= meeting.created_at <= until


def list_visible_teams(client: ParabolClient) -> list[dict]:
    """Return the list of teams visible to the PAT."""
    data = client.query(VIEWER_QUERY)
    return list((data.get("viewer") or {}).get("teams") or [])


def filter_teams(teams: list[dict], wanted: Iterable[str]) -> list[dict]:
    """Filter teams by id OR display name (case-insensitive)."""
    wanted_set = {w.strip().lower() for w in wanted if w and w.strip()}
    if not wanted_set:
        return teams
    return [
        t for t in teams
        if t.get("id", "").lower() in wanted_set
        or t.get("name", "").lower() in wanted_set
    ]


def _to_parabol_dt(dt: datetime) -> str:
    """Format a UTC datetime as the Parabol DateTime scalar requires.

    Parabol's DateTime scalar requires milliseconds:
    YYYY-MM-DDTHH:MM:SS.SSSZ — ISO strings without ms are rejected (HTTP 400).
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def discover_meetings(
    client: ParabolClient,
    teams: list[dict],
    since: datetime,
    until: datetime,
    page_size: int = 25,
) -> list[MeetingSummary]:
    """Walk viewer.meetings and return MeetingSummary records inside [since, until].

    All team IDs are passed in a single query. Pagination advances the upper
    bound (`before`) toward older meetings on each page; `after` stays pinned
    at the user's --since. A seen_ids set defensively dedups boundary rows.
    """
    if not teams:
        return []

    team_id_to_name = {t["id"]: t["name"] for t in teams}
    team_ids = list(team_id_to_name.keys())

    results: list[MeetingSummary] = []
    seen_ids: set[str] = set()
    after_str = _to_parabol_dt(since)
    before_str = _to_parabol_dt(until)
    cursor_before: str = before_str  # advances on each page; starts at the user's --until

    while True:
        variables: dict = {
            "first": page_size,
            "teamIds": team_ids,
            "after": after_str,
            "before": cursor_before,
        }

        data = client.query(TEAM_MEETINGS_QUERY, variables)
        page = (data.get("viewer") or {}).get("meetings") or {}
        edges = page.get("edges") or []

        page_meetings: list[MeetingSummary] = []
        for edge in edges:
            node = edge.get("node") or {}
            if not node:
                continue
            node_id = node.get("id")
            if not node_id or node_id in seen_ids:
                # Defensive dedup. Parabol pagination has shown duplicate-row
                # behavior at boundaries; we drop repeats explicitly so a
                # single surprising response can't double-count meetings.
                continue
            created_raw = node.get("createdAt")
            if not created_raw:
                continue
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            ended_raw = node.get("endedAt")
            ended_at = (
                datetime.fromisoformat(ended_raw.replace("Z", "+00:00"))
                if ended_raw
                else None
            )
            team_id = node.get("teamId", "")
            team_name = team_id_to_name.get(team_id, team_id)
            m = MeetingSummary(
                id=node_id,
                name=node.get("name", "Stand-Up"),
                team_id=team_id,
                team_name=team_name,
                created_at=created_at,
                ended_at=ended_at,
                response_count=int(node.get("responseCount") or 0),
            )
            seen_ids.add(node_id)
            page_meetings.append(m)
            if in_window(m, since, until):
                results.append(m)

        # Advance the upper bound to the oldest meeting on this page so the next
        # call asks for older meetings (Parabol returns newest-first, so the last
        # item in the page is the oldest). pageInfo.endCursor is also acceptable
        # — we use the oldest item we actually saw to avoid surprises if the API
        # ever returns endCursor unset on a non-empty page.
        page_info = page.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        if not page_meetings:
            # API said hasNextPage but we got no new ids. Nothing to advance to.
            break
        oldest_on_page = min(page_meetings, key=lambda m: m.created_at).created_at
        new_before = _to_parabol_dt(oldest_on_page)
        if new_before == cursor_before:
            break
        cursor_before = new_before

    return results
