"""Render MeetingDoc objects to markdown.

Three public entry points:

  render_meeting_filename(doc) -> str
    The filename inside ./out/<run-id>/ for this meeting.

  render_meeting(doc) -> str
    The markdown body for one meeting file.

  render_index(items) -> str
    The INDEX.md body, grouped by team.

All output is plain markdown, safe to pipe into pandoc / GitHub /
Obsidian / etc.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from standup_aggregator.fs import slugify
from standup_aggregator.models import MeetingDoc, Reply, Response


def render_meeting_filename(doc: MeetingDoc) -> str:
    team_slug = slugify(doc.team_name)
    date_slug = doc.created_at.strftime("%Y-%m-%d")
    name_slug = slugify(doc.name)
    return f"{team_slug}--{date_slug}--{name_slug}.md"


def render_meeting(doc: MeetingDoc) -> str:
    parts: list[str] = []
    parts.append(_frontmatter(doc))
    parts.append(_header(doc))
    parts.append(f"> **Prompt:** {doc.prompt}".rstrip())
    parts.append("")
    if not doc.responses:
        parts.append("*No responses recorded.*")
    else:
        for resp in doc.responses:
            parts.append(_response_section(resp))
            parts.append("---")
    return "\n".join(parts).rstrip() + "\n"


def render_index(items: list[tuple[MeetingDoc, str]]) -> str:
    by_team: dict[str, list[tuple[MeetingDoc, str]]] = defaultdict(list)
    for doc, filename in items:
        by_team[doc.team_name].append((doc, filename))

    lines: list[str] = ["# Stand-Ups", ""]
    if not items:
        lines.append("*No meetings in this run.*")
        return "\n".join(lines) + "\n"

    for team_name in sorted(by_team.keys()):
        lines.append(f"## {team_name}")
        lines.append("")
        for doc, filename in sorted(
            by_team[team_name], key=lambda p: p[0].created_at, reverse=True
        ):
            date = doc.created_at.strftime("%Y-%m-%d")
            lines.append(f"- [{doc.name} — {date}]({filename})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _frontmatter(doc: MeetingDoc) -> str:
    ended = doc.ended_at.isoformat() if doc.ended_at else "in progress"
    return (
        "---\n"
        f"meeting_id: {doc.id}\n"
        f"meeting_name: {doc.name}\n"
        f"team: {doc.team_name}\n"
        f"team_id: {doc.team_id}\n"
        f"created_at: {doc.created_at.isoformat()}\n"
        f"ended_at: {ended}\n"
        f"parabol_url: {doc.parabol_url}\n"
        f"response_count: {doc.response_count}\n"
        "---\n"
    )


def _header(doc: MeetingDoc) -> str:
    date = doc.created_at.strftime("%Y-%m-%d")
    return f"# {doc.name} — {doc.team_name} — {date}\n"


def _response_section(resp: Response) -> str:
    lines: list[str] = []
    lines.append(f"## {resp.author_name}")
    lines.append(f"*Posted {resp.created_at.strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append("")
    lines.append(resp.plaintext or "*(empty response)*")
    lines.append("")
    if resp.reactions:
        lines.append("**Reactions:** " + " · ".join(_format_reaction(r) for r in resp.reactions))
        lines.append("")
    if resp.replies:
        lines.append("**Replies:**")
        for reply in resp.replies:
            lines.extend(_render_reply(reply, depth=1))
        lines.append("")
    return "\n".join(lines)


def _format_reaction(reaction) -> str:
    users = ", ".join(reaction.user_names)
    return f"{reaction.emoji_id} ×{reaction.count} ({users})" if users else f"{reaction.emoji_id} ×{reaction.count}"


def _render_reply(reply: Reply, *, depth: int) -> list[str]:
    prefix = "> " * depth
    out = [f"{prefix}**{reply.author_name}** — {reply.plaintext or '*(empty)*'}"]
    if reply.children:
        out.append("> " * depth)  # blank blockquote separator
        for child in reply.children:
            out.extend(_render_reply(child, depth=depth + 1))
    return out
