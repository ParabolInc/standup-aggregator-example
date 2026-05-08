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


def test_render_meeting_quotes_yaml_values_with_colons():
    """Meeting/team names with ':' must remain valid YAML."""
    doc = MeetingDoc(
        id="m1",
        name="Kickoff: Q2",
        team_id="t1",
        team_name="Eng: Platform",
        created_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
        ended_at=None,
        prompt="ok",
        response_count=0,
        responses=[],
    )
    out = render_meeting(doc)
    assert 'meeting_name: "Kickoff: Q2"' in out
    assert 'team: "Eng: Platform"' in out


def test_render_meeting_strips_emoji_namespace():
    """Custom reactjis carry a numeric-namespace prefix; only the shortcode shows."""
    resp = Response(
        id="r1",
        author_name="Bob",
        author_email=None,
        created_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
        plaintext="hi",
        reactions=[Reaction(emoji_id="56572:rocket", count=1, user_names=["Carol"])],
        replies=[],
    )
    out = render_meeting(_doc([resp]))
    assert "rocket ×1 (Carol)" in out
    assert "56572:" not in out


def test_render_meeting_separates_sibling_replies():
    """Two top-level replies render with a blank blockquote between them."""
    r_a = Reply(
        id="c1",
        plaintext="first",
        created_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
        author_name="Alice",
        parent_id=None,
        children=[],
    )
    r_b = Reply(
        id="c2",
        plaintext="second",
        created_at=datetime(2026, 5, 7, 13, 1, tzinfo=UTC),
        author_name="Bob",
        parent_id=None,
        children=[],
    )
    resp = Response(
        id="r1",
        author_name="X",
        author_email=None,
        created_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
        plaintext="x",
        reactions=[],
        replies=[r_a, r_b],
    )
    out = render_meeting(_doc([resp]))
    # Both replies present.
    assert "**Alice** — first" in out
    assert "**Bob** — second" in out
    # A '>' blank-quote line appears between the two reply lines.
    alice_idx = out.index("**Alice** — first")
    bob_idx = out.index("**Bob** — second")
    between = out[alice_idx:bob_idx]
    assert "\n>\n" in between or "\n> \n" in between
