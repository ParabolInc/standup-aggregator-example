# Standup Aggregator — Design

**Date:** 2026-05-07
**Status:** Draft, pending user approval
**Author:** Jordan Husney (with Claude)

## 1. Purpose

A Python 3 CLI that extracts Parabol Stand-Up data (TeamPromptMeeting + responses + threaded replies + reactions) for a configurable date range and writes it to timestamped markdown files under `./out/<run-id>/`.

Above all, this codebase is a **demonstrator of how to use Parabol Personal Access Tokens (PATs)** to call the Parabol GraphQL API. Code clarity, well-commented queries, and an excellent README take precedence over feature breadth.

## 2. Non-goals

- No AI / LLM integration. Bare API calls only.
- No mutation of Parabol state. Read-only.
- No persistent local database. Each run is self-contained under `./out/<run-id>/`.
- No support for meeting types other than `teamPrompt` (Stand-Ups). Action, retro, and poker meetings are out of scope.
- No real-time streaming or webhooks.

## 3. User-facing surface

### 3.1 Installation

```
git clone <repo>
cd standup-aggregator
uv sync
cp .env.example .env   # then fill in PARABOL_PAT
```

### 3.2 Commands

| Command | Purpose |
|---------|---------|
| `standup-aggregator --version` / `--help` | Standard CLI introspection. |
| `standup-aggregator doctor` | Verify PAT auth and list the user's visible teams. |
| `standup-aggregator list [--since X] [--until Y] [--team N]` | Print a Rich table of Stand-Ups in the window without fetching response bodies. |
| `standup-aggregator inspect <meeting-id>` | Hydrate one meeting fully and pretty-print to terminal. Useful for verification and debugging. |
| `standup-aggregator run [--since X] [--until Y] [--team N] [--dry-run]` | The headline command. Discover → hydrate → render to markdown under `./out/<run-id>/`. |

### 3.3 Flags (run / list)

- `--since` — window start. Accepts ISO date (`2026-05-01`), ISO datetime (`2026-05-01T13:00:00Z`), `today`, `yesterday`, or relative `Nd` / `Nw` (e.g., `7d`, `2w`).
- `--until` — window end. Same formats. Defaults to "now".
- `--team` — filter to one or more teams by ID or display name (repeatable).
- `--dry-run` — discover and render in memory but skip file writes.

### 3.4 Defaults

- If neither `--since` nor `--until` is passed: window is **today UTC** (00:00 UTC → now).
- If `--team` not passed: **all teams the PAT can see**, walked in `viewer.teams` order.

### 3.5 Environment

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PARABOL_PAT` | yes | — | Bearer token. Must be prefixed `pat_`. |
| `PARABOL_BASE_URL` | no | `https://action.parabol.co` | Override for self-hosted / staging instances. The GraphQL endpoint is `${BASE_URL}/graphql`. |

## 4. Architecture

### 4.1 Stack rationale

- **uv** — required by user; modern, fast, lockfile-driven.
- **Typer** — pythonic CLI with type-hint-driven flag parsing. Pairs naturally with Rich.
- **Rich** — colored output, spinners, tables, panels. Pretty + modern + colorful (per requirements).
- **httpx** (sync) — single dependency for HTTP. We deliberately do not use a GraphQL client library so readers can see the raw POST + body. Sync is fine; the API surface is small enough that async parallelism isn't required (and would obscure the demonstrator value).
- **python-dateutil** — flexible date parsing for `--since` / `--until`.

### 4.2 Package layout

```
standup-aggregator/
├── pyproject.toml
├── uv.lock
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   └── superpowers/specs/   # this file
├── src/standup_aggregator/
│   ├── __init__.py
│   ├── __main__.py          # python -m standup_aggregator
│   ├── cli.py               # Typer app + command wiring
│   ├── config.py            # env loading, validation, error messages
│   ├── client.py            # ParabolClient: Bearer auth httpx wrapper, GraphQL error surfacing
│   ├── queries.py           # heavily-annotated GraphQL query strings
│   ├── timeparse.py         # --since / --until parsing
│   ├── discover.py          # walk teams, find TeamPromptMeetings in date window
│   ├── fetch.py             # hydrate full meeting (responses + reactjis + thread)
│   ├── models.py            # @dataclass: MeetingDoc, Response, Reply, Reaction
│   ├── render.py            # markdown rendering, INDEX.md, filename slugging
│   ├── fs.py                # run id + ./out/<run-id>/ creation + file I/O
│   └── progress.py          # Rich-based status, spinners, summary table
└── out/                     # generated; gitignored
```

### 4.3 Data flow

```
env (PAT) ──► ParabolClient
                  │
                  ▼
           viewer.teams { id name }       (1 query)
                  │
                  ▼ for each team
           list TeamPromptMeetings        (paginated)
           filter by createdAt window
                  │
                  ▼ for each meeting
           hydrate: meeting + responses + reactjis
                  │
                  ▼ for each response
           hydrate: discussion.thread     (paginated, recursive replies)
                  │
                  ▼
           render markdown + write ./out/<run-id>/<file>.md
                  │
                  ▼
           write INDEX.md + Rich summary
```

### 4.4 Output structure

```
out/2026-05-07-184707/
├── INDEX.md
├── frontend-platform--2026-05-07--daily-standup.md
├── frontend-platform--2026-05-06--daily-standup.md
├── design-system--2026-05-07--standup.md
└── ...
```

- Run ID format: `YYYY-MM-DD-HHmmss` (UTC, zero-padded). Mirrors retro-reflect-bot's pattern.
- Filename: `<team-slug>--<meeting-date>--<meeting-slug>.md`. Slugs are kebab-case, ASCII-only, length-capped to 60 chars per segment to keep total filename < 255 bytes.
- `INDEX.md` lists every generated file grouped under team headings, with date subheadings and links.

### 4.5 Markdown shape (per meeting)

```markdown
---
meeting_id: <id>
meeting_name: <name>
team: <team display name>
team_id: <team id>
created_at: <ISO 8601 UTC>
ended_at: <ISO 8601 UTC or "in progress">
parabol_url: https://action.parabol.co/meet/<meeting-id>
response_count: <int>
---

# <meeting_name> — <team> — <YYYY-MM-DD>

> **Prompt:** <meetingPrompt>

## <user.preferredName>
*Posted <YYYY-MM-DD HH:MM UTC>*

<plaintextContent>

**Reactions:** 👍 ×2 (alice, bob) · 🎉 ×1 (carol)

**Replies:**
> **<replier preferredName>** — <reply plaintext>
>
> > **<nested replier>** — <nested reply plaintext>

---

## <next user> ...
```

Replies use markdown blockquote nesting (one `>` per depth level) so the threading is visible in any markdown renderer.

## 5. Parabol API contract

### 5.1 Authentication

```
POST ${PARABOL_BASE_URL}/graphql
Content-Type: application/json
Authorization: Bearer pat_<token>
```

PATs are validated server-side: prefix-checked for `pat_`, looked up by hash, must have `revokedAt IS NULL` and `expiresAt > now`. The auth context exposes the PAT's scopes; insufficient scope produces a GraphQL error rather than a 401.

**Required scopes:**
- `MEETINGS_READ` — for `viewer`, `Team`, `TeamPromptMeeting`, `TeamPromptResponse`
- `COMMENTS_READ` — for the discussion thread (replies)

### 5.2 Queries (in `queries.py`, each heavily commented)

**`VIEWER_QUERY`** — used by `doctor` and as the entry point for discovery:
```graphql
query Viewer {
  viewer {
    id
    email
    preferredName
    teams { id name }
  }
}
```

**`TEAM_MEETINGS_QUERY`** — list TeamPromptMeetings for one team. Exact shape to be confirmed empirically in Sprint 2 (see §6.1).

**`MEETING_FULL_QUERY`** — hydrate one meeting:
```graphql
query Meeting($meetingId: ID!) {
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
          reactjis {
            id
            count
            users { id preferredName }
          }
        }
        # discussion access path TBD; see §6.2
      }
    }
  }
}
```

**`THREAD_QUERY`** — paginated replies for one response's discussion. Uses `discussion.thread(first, after)` with cursor pagination and recursive `replies` traversal. The navigation path from `TeamPromptResponse` to its `Discussion` is unconfirmed and tracked in §6.2; `THREAD_QUERY`'s final shape depends on that resolution.

### 5.3 Error surfacing

The client raises `ParabolApiError` with three subclasses mapped to friendly messages:

- `AuthError` — 401, missing/expired PAT, missing scope. Message tells the user to check `.env` and the scopes granted on the PAT.
- `NetworkError` — non-2xx HTTP, retried twice on 5xx with exponential backoff.
- `GraphQLError` — `errors[]` array in the response body. The first error's message is shown.

## 6. Known unknowns to resolve during implementation

These are not blocking the design — they're flagged so we don't pretend Sprint 2 will be turn-the-crank work.

### 6.1 Per-team meeting listing

Parabol's GraphQL schema does not expose a top-level "list all meetings in a date range." The Parabol monorepo research surfaced three candidate paths:

1. `team.meetings(...)` — most likely if it exists.
2. `viewer.timeline(after, first, eventTypes: [TimelineEventEnum!])` — works for the viewer only; may miss meetings in teams the viewer didn't participate in.
3. Walk `meetingSeries.prevMeeting` / `nextMeeting` chains — fallback if neither of the above works.

**Resolution plan**: In Sprint 2 we run an introspection query against the live API, pick the cleanest available path, and document the choice in `queries.py`.

### 6.2 Discussion access path

The Parabol monorepo research showed that comments hang off `Discussion`, addressable via `discussion.thread(first, after)`. The exact GraphQL navigation from `TeamPromptResponse` to its discussion needs empirical confirmation: it might be `response.discussion`, or via `phases[].stages[]` of type `TeamPromptResponseStage` whose `discussionId` we resolve with a follow-up query.

**Resolution plan**: Confirm in Sprint 3 with introspection + a single test meeting. Document the chosen path in `queries.py`.

## 7. Sprint plan with verification gates

Each sprint ends with a **manual verification step performed by the user**. The next sprint does not begin until verification passes.

### Sprint 0 — Project scaffold
**Deliverables:**
- `git` initialized, initial commit
- `pyproject.toml` with dependencies, project metadata, console script
- Package layout under `src/standup_aggregator/` with stub modules
- `.env.example`, `.gitignore` (ignores `.env`, `out/`, `__pycache__/`, `.venv/`)
- `--version` and `--help` working through Typer
- Skeleton `README.md`

**Verification:** `uv sync && uv run standup-aggregator --version` succeeds; `--help` renders Typer's colored help.

### Sprint 1 — Auth + GraphQL client + `doctor`
**Deliverables:**
- `config.py` — env loading with friendly errors when `PARABOL_PAT` missing or doesn't start with `pat_`
- `client.py` — `ParabolClient`, `ParabolApiError` hierarchy, retry-on-5xx
- `queries.py` — `VIEWER_QUERY` with field-by-field comments
- `cli.py` — `doctor` command prints user info + visible teams in a Rich panel
- README section: how to mint a PAT in Parabol, what scopes to request

**Verification:** With a real PAT in `.env`, `uv run standup-aggregator doctor` succeeds and shows the user's name/email and team list. Then with a bogus PAT, error message is clear and actionable.

### Sprint 2 — Time range parsing + meeting discovery (highest risk)
**Deliverables:**
- `timeparse.py` — parses ISO date, ISO datetime, `today`, `yesterday`, `Nd`, `Nw`
- Default window resolution: today UTC if neither flag passed
- **Empirical schema check** to resolve §6.1
- `discover.py` — for each team, page through TeamPromptMeetings, return ones whose `createdAt` falls in window
- `list` command — Rich table with columns: team, meeting name, date, response count, meeting ID
- `--team` filter (repeatable) implemented

**Verification:** `uv run standup-aggregator list --since 2026-05-01` prints a recognizable table. Tests: empty range, range with no meetings, wide range, team filter by name, team filter by ID.

### Sprint 3 — Full meeting hydration
**Deliverables:**
- `MEETING_FULL_QUERY` and `THREAD_QUERY` in `queries.py` with comments
- Resolution of §6.2
- `fetch.py` — hydrate a meeting; recursive thread traversal; cursor pagination on threads
- `models.py` — `MeetingDoc`, `Response`, `Reply`, `Reaction` dataclasses
- `inspect <meeting-id>` command — pretty-prints one meeting via Rich

**Verification:** Pick a real meeting from Sprint 2's list; run `inspect <id>`. Confirm prompt, every response, every reply (including nested), and reactions match Parabol's UI.

### Sprint 4 — Markdown rendering + file I/O
**Deliverables:**
- `fs.py` — UTC run-id timestamp, `./out/<run-id>/` auto-created
- `render.py` — markdown per §4.5; nested-blockquote replies; ASCII-safe slugging
- `INDEX.md` generation grouped by team
- `run` command — discover → hydrate → render → write

**Verification:** `uv run standup-aggregator run` produces a real run folder. Open INDEX.md and several meeting files; visually confirm fidelity vs. live Parabol.

### Sprint 5 — Polish + documentation
**Deliverables:**
- `progress.py` — Rich progress bar across teams + spinner per meeting; non-TTY fallback
- End-of-run summary table: teams scanned, meetings, responses, replies, output path
- `--dry-run` flag wired through
- Comprehensive README: PAT minting walkthrough (with screenshots optional), scope guidance, env setup, sample commands, sample output excerpt, troubleshooting section, "how the API works" notes (auth header format, GraphQL error patterns, pagination)
- Inline GraphQL query comments are the demonstrator artifact — review pass for clarity

**Verification:** Read README cold (as if new to Parabol). Run with `--dry-run`, with `--team`, with no flags, and with deliberately bad flags; confirm output is pretty and errors are helpful.

## 8. Testing approach

This is a small CLI demonstrator with most behavior coming from a live external API. We optimize for **runnable verification by the user at each sprint gate** over an automated test suite. We do include lightweight unit tests where they pay off:

- `timeparse.py` — pure function, easy to test, easy to break. Unit tests cover each accepted format and a handful of malformed inputs.
- `render.py` — pure function (model → markdown). Snapshot tests against fixture meetings catch format regressions cheaply.
- `discover.py` window-filter logic — pure given a list of meetings.

We do **not** mock the GraphQL client to test end-to-end flows; verification gates do that for us with the live API.

## 9. Open questions

None — the two open questions raised during brainstorming were resolved by the user:
- Sprint 0 will `git init` the repo as part of the scaffold.
- The Sprint 3 inspect-one-meeting affordance becomes a permanent `inspect <meeting-id>` subcommand rather than throwaway scaffolding.
