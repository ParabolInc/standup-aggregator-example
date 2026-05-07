from datetime import datetime, timezone

from standup_aggregator.fs import mint_run_id, slugify


def test_mint_run_id_is_utc_zero_padded():
    now = datetime(2026, 5, 7, 18, 47, 7, tzinfo=timezone.utc)
    assert mint_run_id(now) == "2026-05-07-184707"


def test_slugify_lowercases_and_kebabs():
    assert slugify("Frontend Platform") == "frontend-platform"


def test_slugify_strips_unicode_and_punctuation():
    assert slugify("Daily Stand-Up! 2026 ✨") == "daily-stand-up-2026"


def test_slugify_collapses_runs_of_separators():
    assert slugify("a   b---c") == "a-b-c"


def test_slugify_returns_fallback_for_empty():
    assert slugify("") == "untitled"


def test_slugify_truncates_long_input():
    long = "a" * 100
    assert len(slugify(long, max_len=60)) == 60
