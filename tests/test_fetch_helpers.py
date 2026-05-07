"""Unit tests for pure helpers in fetch.py.

The full fetch_meeting integrates with a live Parabol API and is verified
manually at sprint gates. These tests cover only the pure logic that
doesn't touch the network: rich-text plaintext extraction and the
flat-list-to-reply-tree pass.
"""

from datetime import datetime, timezone

import pytest

from standup_aggregator.fetch import _build_replies, _extract_plaintext

UTC = timezone.utc


# --- _extract_plaintext ---

def test_extract_plaintext_handles_tiptap_nested():
    content = (
        '{"type":"doc","content":['
        '{"type":"paragraph","content":[{"type":"text","text":"hello world"}]}'
        ']}'
    )
    assert _extract_plaintext(content) == "hello world"


def test_extract_plaintext_handles_tiptap_multiple_paragraphs():
    content = (
        '{"type":"doc","content":['
        '{"type":"paragraph","content":[{"type":"text","text":"first"}]},'
        '{"type":"paragraph","content":[{"type":"text","text":"second"}]}'
        ']}'
    )
    got = _extract_plaintext(content)
    assert "first" in got and "second" in got


def test_extract_plaintext_handles_draft_js_blocks():
    content = '{"blocks":[{"text":"hi there","type":"unstyled"}],"entityMap":{}}'
    assert _extract_plaintext(content) == "hi there"


def test_extract_plaintext_falls_back_for_plain_string():
    assert _extract_plaintext("already plain") == "already plain"


def test_extract_plaintext_handles_none_and_empty():
    assert _extract_plaintext(None) == ""
    assert _extract_plaintext("") == ""


def test_extract_plaintext_skips_non_text_nodes():
    # A mention without inline text should not crash; surrounding text wins.
    content = (
        '{"type":"doc","content":['
        '{"type":"paragraph","content":['
        '{"type":"text","text":"hi "},'
        '{"type":"mention","attrs":{"label":"Alice"}},'
        '{"type":"text","text":" how are you?"}'
        ']}]}'
    )
    got = _extract_plaintext(content)
    assert "hi" in got and "how are you?" in got


# --- _build_replies ---

def _comment(comment_id: str, *, parent: str | None = None, active: bool = True,
             text: str = "ok", at: str = "2026-05-07T12:00:00Z",
             author: str = "Alice") -> dict:
    return {
        "id": comment_id,
        "content": f'{{"type":"doc","content":[{{"type":"paragraph","content":[{{"type":"text","text":"{text}"}}]}}]}}',
        "createdAt": at,
        "createdByUser": {"id": "u1", "preferredName": author},
        "threadParentId": parent,
        "isActive": active,
    }


def test_build_replies_builds_nested_tree():
    nodes = [
        _comment("a", at="2026-05-07T12:00:00Z"),
        _comment("b", parent="a", at="2026-05-07T12:01:00Z"),
        _comment("c", parent="b", at="2026-05-07T12:02:00Z"),
    ]
    top = _build_replies(nodes)
    assert len(top) == 1
    assert top[0].id == "a"
    assert len(top[0].children) == 1
    assert top[0].children[0].id == "b"
    assert top[0].children[0].children[0].id == "c"


def test_build_replies_skips_inactive_nodes():
    nodes = [
        _comment("a", active=True, at="2026-05-07T12:00:00Z"),
        _comment("b", active=False, at="2026-05-07T12:01:00Z"),
    ]
    top = _build_replies(nodes)
    assert [r.id for r in top] == ["a"]


def test_build_replies_promotes_orphan_to_top_level():
    # Reply 'b' refers to a parent 'missing' that was never present
    # (e.g., parent was filtered out as inactive). 'b' surfaces at top.
    nodes = [
        _comment("b", parent="missing", at="2026-05-07T12:00:00Z"),
    ]
    top = _build_replies(nodes)
    assert [r.id for r in top] == ["b"]


def test_build_replies_sorts_by_created_at_at_each_level():
    nodes = [
        _comment("late", at="2026-05-07T13:00:00Z"),
        _comment("early", at="2026-05-07T12:00:00Z"),
    ]
    top = _build_replies(nodes)
    assert [r.id for r in top] == ["early", "late"]
