"""Discover TeamPromptMeetings (Stand-Ups) inside a date window.

Strategy (confirmed by introspection against live API):

  The Parabol schema does NOT have a per-team paginated meetings field.
  Instead, the viewer-level User.meetings field accepts:

    meetings(first, teamIds, meetingTypes, after, before)

  where `before` is a required DateTime, `after` is an optional DateTime
  cursor (from pageInfo.endCursor of the previous page), and both
  `teamIds` and `meetingTypes` are required non-null lists.

  DateTime scalars MUST include milliseconds in the format:
  YYYY-MM-DDTHH:MM:SS.SSSZ — the server rejects ISO strings without ms.

  Pagination uses DateTime-based cursors (not opaque relay strings).
  pageInfo.endCursor is a DateTime string; pass it as `after` on the
  next call. Stop when pageInfo.hasNextPage is false.

  Discovery flow:
  1. Query VIEWER_QUERY for the list of teams visible to the PAT.
  2. Optionally filter to --team flags (by id or display name).
  3. Pass all surviving team IDs to TEAM_MEETINGS_QUERY in one request,
     paginating until hasNextPage is false. The API server-side filters
     to the requested teams, so no client-side grouping by teamId is
     needed — but we do need a lookup map to resolve team names.
  4. Filter each page's meetings client-side to the [since, until]
     window (inclusive on both ends), since the API window is set by
     the outer [since, until] and the cursor only narrows the `after`.

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

    All team IDs are passed in a single query. Pagination uses DateTime-based
    cursors — endCursor from pageInfo is fed back as `after` on the next call.
    """
    if not teams:
        return []

    team_id_to_name = {t["id"]: t["name"] for t in teams}
    team_ids = list(team_id_to_name.keys())

    results: list[MeetingSummary] = []
    cursor: str | None = None

    before_str = _to_parabol_dt(until)
    since_str = _to_parabol_dt(since)

    while True:
        variables: dict = {
            "first": page_size,
            "teamIds": team_ids,
            "before": before_str,
        }
        # `after` is optional (nullable DateTime) — only include when paginating
        if cursor is not None:
            variables["after"] = cursor
        else:
            # Use since as the initial `after` so the server filters server-side
            variables["after"] = since_str

        data = client.query(TEAM_MEETINGS_QUERY, variables)
        page = (data.get("viewer") or {}).get("meetings") or {}
        edges = page.get("edges") or []

        for edge in edges:
            node = edge.get("node") or {}
            if not node:
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
                id=node["id"],
                name=node.get("name", "Stand-Up"),
                team_id=team_id,
                team_name=team_name,
                created_at=created_at,
                ended_at=ended_at,
                response_count=int(node.get("responseCount") or 0),
            )
            if in_window(m, since, until):
                results.append(m)

        page_info = page.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        new_cursor = page_info.get("endCursor")
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor

    return results
