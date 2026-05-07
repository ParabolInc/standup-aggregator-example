from datetime import datetime, timezone

from standup_aggregator.models import MeetingDoc, Reaction, Reply, Response
from standup_aggregator.render import render_index, render_meeting, render_meeting_filename

UTC = timezone.utc


def _doc(responses=None) -> MeetingDoc:
    return MeetingDoc(
        id="m1",
        name="Daily Standup",
        team_id="t1",
        team_name="Frontend Platform",
        created_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 7, 13, 14, 22, tzinfo=UTC),
        prompt="What's on your plate today?",
        response_count=len(responses or []),
        responses=responses or [],
    )


def test_filename_combines_team_date_meeting_slug():
    doc = _doc()
    assert render_meeting_filename(doc) == "frontend-platform--2026-05-07--daily-standup.md"


def test_render_meeting_includes_frontmatter_keys():
    doc = _doc()
    out = render_meeting(doc)
    assert out.startswith("---\n")
    for key in ("meeting_id:", "meeting_name:", "team:", "team_id:", "created_at:", "parabol_url:"):
        assert key in out


def test_render_meeting_includes_prompt_as_blockquote():
    out = render_meeting(_doc())
    assert "> **Prompt:** What's on your plate today?" in out


def test_render_meeting_renders_response_with_reactions_and_replies():
    reply_b = Reply(
        id="c2",
        plaintext="Yes please.",
        created_at=datetime(2026, 5, 7, 13, 5, tzinfo=UTC),
        author_name="Alice",
        parent_id="c1",
        children=[],
    )
    reply_a = Reply(
        id="c1",
        plaintext="Want to pair?",
        created_at=datetime(2026, 5, 7, 13, 4, tzinfo=UTC),
        author_name="Bob",
        parent_id=None,
        children=[reply_b],
    )
    resp = Response(
        id="r1",
        author_name="Alice",
        author_email="alice@example.com",
        created_at=datetime(2026, 5, 7, 13, 2, tzinfo=UTC),
        plaintext="Wrapping up the auth refactor.",
        reactions=[Reaction(emoji_id="thumbsup", count=2, user_names=["Bob", "Carol"])],
        replies=[reply_a],
    )
    out = render_meeting(_doc([resp]))
    assert "## Alice" in out
    assert "Wrapping up the auth refactor." in out
    assert "thumbsup ×2 (Bob, Carol)" in out
    assert "> **Bob** — Want to pair?" in out
    # Nested reply rendered under double blockquote.
    assert "> > **Alice** — Yes please." in out


def test_render_index_groups_files_under_team_headings():
    doc1 = _doc()
    doc2 = _doc()
    files = [(doc1, "a.md"), (doc2, "b.md")]
    out = render_index(files)
    assert "# Stand-Ups" in out
    assert "## Frontend Platform" in out
    assert "[Daily Standup — 2026-05-07](a.md)" in out
