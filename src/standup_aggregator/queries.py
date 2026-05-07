"""GraphQL query strings for Parabol's public API.

The strings live here so readers can audit exactly which fields we
request. Each query carries a docstring-style comment explaining its
purpose, the scopes it requires, and the shape of its response.

Why no GraphQL client library? Because this codebase is a demonstrator.
You should be able to copy a query from here and paste it into the
Parabol GraphiQL explorer and have it work.

GraphiQL: https://action.parabol.co/graphql (when authenticated)
"""

from __future__ import annotations

# Used by the `doctor` command and as the entry point for discovery.
#
# Required scope: MEETINGS_READ (just to read your own profile + teams).
#
# Returns:
#   data.viewer.id            (str)        the authenticated user's id
#   data.viewer.email         (str)
#   data.viewer.preferredName (str)        the display name shown in Parabol
#   data.viewer.teams[].id    (str)        every team this PAT can see
#   data.viewer.teams[].name  (str)
VIEWER_QUERY = """
query Viewer {
  viewer {
    id
    email
    preferredName
    teams {
      id
      name
    }
  }
}
"""
