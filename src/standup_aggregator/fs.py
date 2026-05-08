"""Filesystem helpers: run id, output directory, slugging.

Each invocation of `run` produces a fresh ./out/<run-id>/ directory.
The run id is a UTC timestamp, zero-padded, suitable for sorting and
safe for filesystems.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

DEFAULT_OUT_ROOT = Path("./out")


def mint_run_id(now: datetime) -> str:
    """Return a UTC YYYY-MM-DD-HHmmss run id."""
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware")
    return now.strftime("%Y-%m-%d-%H%M%S")


def make_run_dir(run_id: str, root: Path = DEFAULT_OUT_ROOT) -> Path:
    """Create and return ./out/<run-id>/."""
    path = root / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str, *, max_len: int = 60) -> str:
    """Return a kebab-case ASCII slug, length-capped, never empty.

    Steps: NFKD-normalize, drop non-ASCII, lowercase, replace
    anything not [a-z0-9] with '-', collapse runs, trim '-' from ends,
    truncate.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered)
    trimmed = replaced.strip("-")
    if not trimmed:
        return "untitled"
    return trimmed[:max_len].rstrip("-") or "untitled"
