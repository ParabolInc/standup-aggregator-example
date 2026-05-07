"""Hydrate one TeamPromptMeeting into a fully-loaded MeetingDoc.

Schema deviations from plan (confirmed by introspection 2026-05-07):
  1. Discussion is on TeamPromptResponseStage, NOT on TeamPromptResponse.
     We walk meeting.phases[TeamPromptResponsesPhase].stages[TeamPromptResponseStage]
     to build a {response_id -> discussion} map, then join it against responses.
  2. Comment has no .plaintextContent field. The field is .content (rich-text string).
  3. Parabol enforces a query depth limit of 12. Embedding threads inline inside
     the meeting query would exceed it (depth 14). Therefore MEETING_FULL_QUERY
     fetches only discussion id + commentCount, and THREAD_QUERY is called per
     discussion that has comments.

Two GraphQL calls per response that has comments (typical case):
  1. MEETING_FULL_QUERY — the meeting + responses + per-stage discussion ids.
  2. THREAD_QUERY — one call per non-empty discussion, paginating until done.
"""

from __future__ import annotations

from datetime import datetime

from standup_aggregator.client import ParabolClient
from standup_aggregator.models import MeetingDoc, Reaction, Reply, Response
from standup_aggregator.queries import MEETING_FULL_QUERY, THREAD_QUERY

THREAD_PAGE_SIZE = 50


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _build_replies(comment_nodes: list[dict]) -> list[Reply]:
    """Group flat comment list into a tree by threadParentId."""
    by_id: dict[str, Reply] = {}
    for node in comment_nodes:
        if not node.get("isActive", True):
            continue
        author = (node.get("createdByUser") or {}).get("preferredName") or "(unknown)"
        created = _parse_dt(node.get("createdAt"))
        if created is None:
            continue
        reply = Reply(
            id=node["id"],
            plaintext=node.get("content") or "",  # Comment.content, not .plaintextContent
            created_at=created,
            author_name=author,
            parent_id=node.get("threadParentId"),
            children=[],
        )
        by_id[reply.id] = reply

    top_level: list[Reply] = []
    for reply in by_id.values():
        parent_id = reply.parent_id
        if parent_id and parent_id in by_id:
            by_id[parent_id].children.append(reply)
        else:
            top_level.append(reply)

    def _sort_tree(rs: list[Reply]) -> None:
        rs.sort(key=lambda r: r.created_at)
        for r in rs:
            _sort_tree(r.children)

    _sort_tree(top_level)
    return top_level


def _fetch_all_comments(client: ParabolClient, discussion_id: str) -> list[dict]:
    """Fetch all comment nodes for a discussion, paginating as needed."""
    comment_nodes: list[dict] = []
    cursor: str | None = None

    while True:
        data = client.query(
            THREAD_QUERY,
            {
                "discussionId": discussion_id,
                "first": THREAD_PAGE_SIZE,
                "after": cursor,
            },
        )
        thread = ((data.get("viewer") or {}).get("discussion") or {}).get("thread") or {}
        for edge in thread.get("edges") or []:
            node = edge.get("node")
            if node:
                comment_nodes.append(node)
        page_info = thread.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        new_cursor = page_info.get("endCursor")
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor

    return comment_nodes


def fetch_meeting(client: ParabolClient, meeting_id: str) -> MeetingDoc:
    """Hydrate a single meeting by id."""
    data = client.query(
        MEETING_FULL_QUERY,
        {"meetingId": meeting_id},
    )
    meeting = (data.get("viewer") or {}).get("meeting") or {}
    if not meeting:
        raise ValueError(f"No TeamPromptMeeting found for id {meeting_id!r}")

    team = meeting.get("team") or {}

    # Build response_id → discussion dict by walking phases → stages.
    # Discussion lives on TeamPromptResponseStage, not on TeamPromptResponse.
    response_to_discussion: dict[str, dict] = {}
    for phase in meeting.get("phases") or []:
        for stage in phase.get("stages") or []:
            response_ref = stage.get("response") or {}
            resp_id = response_ref.get("id")
            discussion = stage.get("discussion")
            if resp_id and discussion:
                response_to_discussion[resp_id] = discussion

    responses_raw = meeting.get("responses") or []
    responses: list[Response] = []

    for r in responses_raw:
        user = r.get("user") or {}
        reactions = [
            Reaction(
                emoji_id=rj.get("id", ""),
                count=int(rj.get("count") or 0),
                user_names=[(u.get("preferredName") or "") for u in (rj.get("users") or [])],
            )
            for rj in r.get("reactjis") or []
        ]

        response_id = r.get("id")
        if not response_id:
            continue

        # Fetch thread for this response's discussion, if any.
        discussion = response_to_discussion.get(response_id) or {}
        comment_count = int(discussion.get("commentCount") or 0)
        comment_nodes: list[dict] = []
        if comment_count > 0 and discussion.get("id"):
            comment_nodes = _fetch_all_comments(client, discussion["id"])

        responses.append(
            Response(
                id=response_id,
                author_name=user.get("preferredName") or "(unknown)",
                author_email=user.get("email"),
                created_at=_parse_dt(r.get("createdAt")) or _parse_dt(meeting.get("createdAt")),
                plaintext=r.get("plaintextContent") or "",
                reactions=reactions,
                replies=_build_replies(comment_nodes),
            )
        )

    meeting_id_value = meeting.get("id")
    if not meeting_id_value:
        raise ValueError(f"Meeting {meeting_id!r} returned without an id field")

    return MeetingDoc(
        id=meeting_id_value,
        name=meeting.get("name", "Stand-Up"),
        team_id=team.get("id") or meeting.get("teamId", ""),
        team_name=team.get("name") or "(unknown team)",
        created_at=_parse_dt(meeting.get("createdAt")),
        ended_at=_parse_dt(meeting.get("endedAt")),
        prompt=meeting.get("meetingPrompt") or "",
        response_count=int(meeting.get("responseCount") or len(responses)),
        responses=responses,
    )
