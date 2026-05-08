"""Load and validate runtime configuration from environment variables.

Configuration source of truth is the user's environment, optionally
populated from a .env file at the working directory. We only read two
variables:

  PARABOL_PAT       (required) The Personal Access Token, prefix 'pat_'.
  PARABOL_BASE_URL  (optional) Defaults to the Parabol SaaS instance.

We deliberately keep this tiny — it's a demo. No layered config files,
no profile system. If you need more, fork.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://action.parabol.co"
PAT_PREFIX = "pat_"


class ConfigError(RuntimeError):
    """Raised when required config is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration for the current invocation."""

    pat: str
    base_url: str

    @property
    def graphql_url(self) -> str:
        return f"{self.base_url}/graphql"


def load_config() -> Config:
    """Read environment (and .env if present) and return a validated Config.

    Raises ConfigError with an actionable message if anything is missing.
    """
    load_dotenv()  # safe no-op if .env doesn't exist

    pat = os.environ.get("PARABOL_PAT", "").strip()
    if not pat:
        raise ConfigError(
            "PARABOL_PAT is not set. Add it to your .env file or export it.\n"
            "Mint a PAT at: https://action.parabol.co/me/profile/personal-access-tokens"
        )
    if not pat.startswith(PAT_PREFIX):
        raise ConfigError(
            f"PARABOL_PAT must start with '{PAT_PREFIX}'. The value you provided does not.\n"
            "If you copied an OAuth access token, that won't work — you need a PAT."
        )

    base_url = os.environ.get("PARABOL_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL

    return Config(pat=pat, base_url=base_url)
