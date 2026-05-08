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
# Pagination: advance the upper bound (`before`) on each page. Parabol returns
# results newest-first and treats `after` as a fixed lower-bound date filter —
# NOT a forward-paging cursor. Passing endCursor back as `after` would return
# the same meetings inclusively (duplicating every row). Instead, `after` stays
# pinned at the user's --since for every call; `before` is advanced to the
# createdAt of the oldest meeting on the previous page to request older records.
# Stop when `pageInfo.hasNextPage` is false or no progress can be made.
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

# Hydrate one TeamPromptMeeting with all its responses, reactions, and the
# discussion id attached to each response (via the stage that owns the response).
#
# SCHEMA PATH (confirmed by introspection, 2026-05-07):
#   Variant B — discussion is on TeamPromptResponseStage, NOT on TeamPromptResponse.
#   Introspection of TeamPromptResponse showed fields: id, reactjis, userId, user,
#   content, plaintextContent, createdAt, updatedAt, sortOrder — no discussion field.
#   Introspection of TeamPromptResponseStage confirmed: discussion: Discussion! (NON_NULL).
#
# WHY THREADS ARE NOT INLINE:
#   Parabol enforces a query depth limit of 12. Embedding thread edges inline inside
#   phases → stages → discussion → thread → edges → node → createdByUser would exceed
#   that limit (depth 14 with the outer viewer.meeting path). Threads are therefore
#   fetched per-discussion with a separate THREAD_QUERY call after the meeting loads.
#
# NOTE: Comment.content is rich text (Parabol's internal draft-js format string).
#   There is no Comment.plaintextContent field — the plan's template was wrong.
#   We read Comment.content directly; the render layer displays it as-is.
#
# Required scopes: MEETINGS_READ.
#
# Returns:
#   viewer.meeting.id / name / createdAt / endedAt / teamId / team / meetingPrompt /
#   responseCount / responses[] (with user and reactjis) /
#   phases[TeamPromptResponsesPhase].stages[TeamPromptResponseStage].response.id +
#   discussion.id + discussion.commentCount
MEETING_FULL_QUERY = """
query MeetingFull($meetingId: ID!) {
  viewer {
    meeting(meetingId: $meetingId) {
      ... on TeamPromptMeeting {
        id
        name
        createdAt
        endedAt
        teamId
        team { id name }
        meetingPrompt
        responseCount
        responses {
          id
          userId
          user { id preferredName email }
          plaintextContent
          createdAt
          updatedAt
          reactjis { id count users { id preferredName } }
        }
        phases {
          phaseType
          ... on TeamPromptResponsesPhase {
            stages {
              ... on TeamPromptResponseStage {
                response { id }
                discussion { id commentCount }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Continue paginating one discussion's thread.
#
# viewer.discussion(id: ID!) confirmed by introspection of User type:
#   discussion: Discussion (nullable OBJECT), arg: id: ID! (NON_NULL).
#
# Required scope: COMMENTS_READ.
#
# Comment.content is Parabol's rich-text (draft-js) string. threadParentId
# links replies to their parent comment. isActive filters deleted comments.
THREAD_QUERY = """
query DiscussionThread($discussionId: ID!, $first: Int!, $after: String) {
  viewer {
    discussion(id: $discussionId) {
      id
      thread(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            ... on Comment {
              id
              content
              createdAt
              createdByUser { id preferredName }
              threadParentId
              isActive
            }
          }
        }
      }
    }
  }
}
"""
