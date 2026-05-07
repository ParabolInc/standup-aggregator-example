"""Thin GraphQL client around httpx.

This file is intentionally simple and verbose. It is a demonstrator for
how to authenticate with Parabol using a Personal Access Token (PAT).
There is no GraphQL library here on purpose — every wire concern is in
plain view.

Wire format:

  POST {base_url}/graphql
  Content-Type: application/json
  Authorization: Bearer pat_xxx
  body: {"query": "...", "variables": {...}}

Response:

  HTTP 200 with body {"data": {...}, "errors": [{message: str, ...}]}
  Even server errors typically return 200 — failures live in body.errors.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from standup_aggregator.config import Config


class ParabolApiError(RuntimeError):
    """Base class for any Parabol API failure."""


class AuthError(ParabolApiError):
    """PAT missing, expired, revoked, or lacking required scopes."""


class NetworkError(ParabolApiError):
    """Non-2xx HTTP, DNS failure, timeout — anything below the API layer."""


class GraphQLError(ParabolApiError):
    """The API returned a structured error in the response body."""

    def __init__(self, messages: list[str]):
        super().__init__("; ".join(messages) or "GraphQL error")
        self.messages = messages


class ParabolClient:
    """A small synchronous Parabol GraphQL client.

    Construct one per process. It opens an httpx client lazily on the
    first call and reuses the connection pool across queries.
    """

    DEFAULT_TIMEOUT_SECONDS = 30.0
    MAX_RETRIES = 2  # for transient 5xx
    RETRY_BACKOFF_SECONDS = 1.0

    def __init__(self, config: Config) -> None:
        self._config = config
        self._http: httpx.Client | None = None

    def __enter__(self) -> "ParabolClient":
        self._http = httpx.Client(timeout=self.DEFAULT_TIMEOUT_SECONDS)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL operation and return its `data` payload."""
        if self._http is None:
            raise RuntimeError("ParabolClient must be used as a context manager.")

        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.pat}",
        }

        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self._http.post(
                    self._config.graphql_url,
                    headers=headers,
                    json=payload,
                )
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                raise NetworkError(f"Network failure calling Parabol: {exc}") from exc

            if response.status_code in (401, 403):
                raise AuthError(
                    f"Parabol rejected the PAT (HTTP {response.status_code}). "
                    "Check that your PARABOL_PAT is valid, not revoked, not expired, "
                    "and that it was issued with the required scopes (MEETINGS_READ, COMMENTS_READ)."
                )

            if 500 <= response.status_code < 600:
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                raise NetworkError(
                    f"Parabol returned HTTP {response.status_code} after retries: "
                    f"{response.text[:200]}"
                )

            if not response.is_success:
                raise NetworkError(
                    f"Parabol returned HTTP {response.status_code}: {response.text[:200]}"
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise NetworkError(f"Parabol returned non-JSON body: {response.text[:200]}") from exc

            errors = body.get("errors") or []
            if errors:
                messages = [e.get("message", "(no message)") for e in errors]
                # Heuristic: scope-related errors typically mention 'scope' or 'permission'.
                joined = " ".join(messages).lower()
                if "scope" in joined or "permission" in joined or "unauthorized" in joined:
                    raise AuthError("; ".join(messages))
                raise GraphQLError(messages)

            return body.get("data") or {}

        # If we drained the loop without returning, surface the last exception.
        raise NetworkError(f"Exhausted retries: {last_exc}")
