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

# Lists TeamPromptMeetings across specified teams in a date window.
#
# Template choice: viewer.meetings(first, teamIds, meetingTypes, after, before).
# Introspection confirmed that Team has no paginated meetings field; instead the
# viewer-level `meetings` field accepts teamIds + meetingTypes + DateTime range.
#
# Required scope: MEETINGS_READ.
#
# Pagination: DateTime-cursor style. `pageInfo.endCursor` is a DateTime string
# (YYYY-MM-DDTHH:MM:SS.SSSZ). Pass it as `after` on the next call. Stop when
# `pageInfo.hasNextPage` is false.
#
# IMPORTANT: Both `after` and `before` accept DateTime scalars that MUST include
# milliseconds: YYYY-MM-DDTHH:MM:SS.SSSZ (e.g. 2026-05-01T00:00:00.000Z).
# ISO strings without milliseconds are rejected by the server with a 400 error.
# `before` is NON_NULL (required); `after` is nullable.
#
# Returns:
#   data.viewer.meetings.pageInfo.hasNextPage  (bool)
#   data.viewer.meetings.pageInfo.endCursor    (str | null, DateTime format)
#   data.viewer.meetings.edges[].cursor        (str, DateTime of createdAt)
#   data.viewer.meetings.edges[].node.id       (str)
#   data.viewer.meetings.edges[].node.name     (str)
#   data.viewer.meetings.edges[].node.createdAt (str, ISO 8601 with ms)
#   data.viewer.meetings.edges[].node.endedAt   (str | null)
#   data.viewer.meetings.edges[].node.teamId    (str)
#   data.viewer.meetings.edges[].node.responseCount (int)
TEAM_MEETINGS_QUERY = """
query TeamMeetings($first: Int!, $teamIds: [ID!]!, $after: DateTime, $before: DateTime!) {
  viewer {
    meetings(first: $first, teamIds: $teamIds, meetingTypes: [teamPrompt], after: $after, before: $before) {
      pageInfo { hasNextPage endCursor }
      edges {
        cursor
        node {
          ... on TeamPromptMeeting {
            id
            name
            createdAt
            endedAt
            teamId
            responseCount
          }
        }
      }
    }
  }
}
"""
