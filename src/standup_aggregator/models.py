"""Typed in-memory representation of a hydrated Stand-Up meeting.

Layered: Reaction sits inside Response; Reply is a thread comment that
may be a reply to another reply; MeetingDoc is the root.

These dataclasses are intentionally simple — no validation, no methods.
They are the bridge between the GraphQL response shape (fetch.py) and
the markdown output (render.py). When the GraphQL shape evolves, fix
fetch.py only — render.py works against this model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Reaction:
    emoji_id: str  # e.g. "thumbsup"
    count: int
    user_names: list[str]


@dataclass(frozen=True, slots=True)
class Reply:
    id: str
    plaintext: str
    created_at: datetime
    author_name: str
    parent_id: str | None  # None for top-level reply, else the parent Reply.id
    children: list["Reply"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Response:
    id: str
    author_name: str
    author_email: str | None
    created_at: datetime
    plaintext: str
    reactions: list[Reaction]
    replies: list[Reply]  # top-level only; nesting via Reply.children


@dataclass(frozen=True, slots=True)
class MeetingDoc:
    id: str
    name: str
    team_id: str
    team_name: str
    created_at: datetime
    ended_at: datetime | None
    prompt: str
    response_count: int
    responses: list[Response]

    @property
    def parabol_url(self) -> str:
        return f"https://action.parabol.co/meet/{self.id}"
