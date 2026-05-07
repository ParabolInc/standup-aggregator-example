"""Parse --since / --until CLI flags into UTC-aware datetimes.

Accepted forms:

  ISO 8601 date:     2026-05-01
  ISO 8601 datetime: 2026-05-01T13:30:00Z, 2026-05-01T13:30:00+00:00
  Keyword:           today, yesterday   (anchor to UTC midnight)
  Relative:          Nd (N days ago), Nw (N weeks ago)

All returned datetimes are timezone-aware UTC. Naive ISO datetimes are
treated as UTC. The caller is responsible for any further normalization.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as dateutil_parser

UTC = timezone.utc

DEFAULT_WINDOW_DESCRIPTION = "today UTC (00:00 to now)"

_RELATIVE_RE = re.compile(r"^\s*(?P<n>\d+)\s*(?P<unit>[dw])\s*$", re.IGNORECASE)


class TimeParseError(ValueError):
    """Raised when a --since/--until value cannot be parsed."""


def _utc_midnight(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day, tzinfo=UTC)


def parse_when(value: str, *, now: datetime) -> datetime:
    """Parse a single time expression. `now` is required for relative forms."""
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware")

    s = value.strip()
    if not s:
        raise TimeParseError("empty value")

    lower = s.lower()
    if lower == "today":
        return _utc_midnight(now)
    if lower == "yesterday":
        return _utc_midnight(now) - timedelta(days=1)

    m = _RELATIVE_RE.match(s)
    if m:
        n = int(m.group("n"))
        unit = m.group("unit").lower()
        delta = timedelta(days=n) if unit == "d" else timedelta(weeks=n)
        return now - delta

    try:
        parsed = dateutil_parser.isoparse(s)
    except (ValueError, TypeError) as exc:
        raise TimeParseError(
            f"Can't understand {value!r}. Use ISO date (2026-05-01), "
            "ISO datetime (2026-05-01T13:30:00Z), 'today', 'yesterday', or '7d'/'2w'."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed


def parse_window(
    since: str | None,
    until: str | None,
    *,
    now: datetime,
) -> tuple[datetime, datetime, str]:
    """Resolve a (since, until, description) triple from optional CLI flags.

    If neither flag is provided, the window is today UTC (00:00 → now)
    and the description reflects that. The description is intended for
    one-line user-facing logging.
    """
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware")

    is_default = since is None and until is None

    resolved_since = parse_when(since, now=now) if since else _utc_midnight(now)
    resolved_until = parse_when(until, now=now) if until else now

    if resolved_until < resolved_since:
        raise TimeParseError(
            f"--until ({resolved_until.isoformat()}) is before --since ({resolved_since.isoformat()})."
        )

    if is_default:
        description = DEFAULT_WINDOW_DESCRIPTION
    else:
        description = f"{resolved_since.isoformat()} → {resolved_until.isoformat()}"

    return resolved_since, resolved_until, description
