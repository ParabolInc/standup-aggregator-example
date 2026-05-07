# standup-aggregator

A small Python CLI that pulls [Parabol](https://parabol.co) Stand-Up data (TeamPromptMeetings) for a date range and writes one markdown file per meeting under `./out/<run-id>/`.

This codebase doubles as a **demonstrator for Parabol Personal Access Tokens (PATs)**. The GraphQL queries are annotated, the auth flow is in plain view, and this README explains how Parabol's API works.

## Why this exists

- Drop a few hundred lines of code that show, end-to-end, how to call the public Parabol GraphQL API with a PAT.
- Produce useful output (markdown digests of recent Stand-Ups) along the way.
- Stay small enough to read top-to-bottom in one sitting.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- A Parabol account on [action.parabol.co](https://action.parabol.co) (or self-hosted)

## Install

```bash
uv sync
```

## Mint a Personal Access Token

1. Sign in to Parabol.
2. Go to **Profile → Personal Access Tokens** (`/me/profile/personal-access-tokens`).
3. Click **Create token**.
4. Required scopes:
   - `MEETINGS_READ` — meetings, prompts, responses.
   - `COMMENTS_READ` — reply threads.
5. Copy the token (`pat_...`). You will only see it once.

```bash
cp .env.example .env
# Edit .env, paste your PAT into PARABOL_PAT=
```

For self-hosted Parabol, also set `PARABOL_BASE_URL=https://your.parabol.example`.

## Commands

```bash
uv run standup-aggregator --help
```

| Command | What it does |
|---------|--------------|
| `doctor` | Verify your PAT and list teams it can see. |
| `list [--since X --until Y --team ...]` | Print a table of Stand-Ups in the window without fetching responses. |
| `inspect <meeting-id>` | Hydrate one meeting fully and pretty-print to terminal. |
| `run [--since X --until Y --team ... --dry-run]` | Hydrate every Stand-Up in the window and write to `./out/<run-id>/`. |

### Time-range flags

`--since` and `--until` accept:

- ISO date: `2026-05-01`
- ISO datetime: `2026-05-01T13:30:00Z`
- Keywords: `today`, `yesterday`
- Relative: `7d` (7 days ago), `2w` (2 weeks ago)

If neither is provided, the window is **today UTC** (00:00 UTC → now).

### Examples

```bash
uv run standup-aggregator doctor

uv run standup-aggregator list --since 7d
uv run standup-aggregator list --since 2026-05-01 --team "Frontend Platform"

uv run standup-aggregator run --since yesterday
uv run standup-aggregator run --since 2026-05-01 --until 2026-05-07
uv run standup-aggregator run --since 14d --dry-run
```

## Output

Each `run` produces a folder:

```
out/2026-05-07-184707/
├── INDEX.md
├── frontend-platform--2026-05-07--daily-standup.md
├── frontend-platform--2026-05-06--daily-standup.md
└── ...
```

Each meeting file has YAML frontmatter (id, team, timestamps, Parabol URL) followed by the prompt, every response with its reactions, and any reply threads (rendered with nested blockquotes for thread depth).

A run also prints a green-bordered "Run summary" table to the terminal when it finishes:

```
            Run summary
   ╭───────────────┬───────────╮
   │ Teams scanned │     3     │
   │ Meetings written │   12   │
   │ Responses     │    87     │
   │ Replies       │    14     │
   │ Output        │ out/...   │
   ╰───────────────┴───────────╯
```

## How the API works

This is the demonstrator part. If you came here to learn how to call Parabol from your own code, here's the short tour.

**Endpoint.** `POST https://action.parabol.co/graphql`. Self-hosted? Set `PARABOL_BASE_URL` and `${BASE_URL}/graphql` is used.

**Auth header.** `Authorization: Bearer pat_<token>`. The PAT is validated server-side (prefix, hash lookup, revoked/expired checks); insufficient scope produces a GraphQL error in the response body, not an HTTP 401.

**Errors.** Parabol generally returns HTTP 200 even for failures, with an `errors` array in the JSON body. We classify into:
- `AuthError` — HTTP 401/403, or messages mentioning "scope"/"unauthorized".
- `NetworkError` — non-2xx HTTP, retried twice on 5xx with a 1s/2s backoff.
- `GraphQLError` — anything else returned in `errors`.

**Pagination.**
- `viewer.meetings(after, before, ...)` is **not** Relay-style: `after` and `before` are date-range filters (lower/upper bound), not opaque cursors. To page across a wide date range we keep `after` fixed at `--since` and advance `before` toward older meetings on each page. A `seen_ids` set defensively dedupes if the API surprises us at boundaries.
- Discussion threads (`Discussion.thread(first, after)`) **are** Relay-style with cursor `endCursor`.

**Schema gotchas worth knowing.**
- Parabol's `DateTime` scalar **requires millisecond precision** (`.000Z`). Strings like `2026-05-01T00:00:00Z` are rejected with HTTP 400. See `_to_parabol_dt` in `discover.py`.
- Parabol enforces a **GraphQL query depth limit of 12**. Hydrating a meeting with its threads inline exceeds that, so we split into `MEETING_FULL_QUERY` (just discussion ids) and per-discussion `THREAD_QUERY` calls.
- `TeamPromptResponse` has **no** `discussion` field. Discussion lives on `TeamPromptResponseStage`. We walk `meeting.phases[].stages[]` and join by `response.id`.
- `Comment` has no `plaintextContent` field — only `content`, which is a stringified rich-text JSON document (TipTap / Prosemirror). The `_extract_plaintext` helper in `fetch.py` walks the tree and collects text leaves. Note the asymmetry: `TeamPromptResponse` exposes `plaintextContent` directly, so we don't need an extractor for response bodies — only for comments and replies.
- Custom emoji reactions (reactjis) carry an `<orgId>:<shortcode>` id. Strip the prefix for rendering.

**The queries we use** are in [`src/standup_aggregator/queries.py`](src/standup_aggregator/queries.py). Open that file. Every query has a docstring explaining its purpose, scopes, and return shape — they're meant to be read.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Config error: PARABOL_PAT is not set.` | `.env` missing or var not exported. |
| `PARABOL_PAT must start with 'pat_'.` | You used an OAuth token instead of a PAT. |
| `Parabol rejected the PAT (HTTP 401).` | Token revoked, expired, or scopes missing. |
| `API error: ... scope ...` | PAT lacks `MEETINGS_READ` or `COMMENTS_READ`. Re-mint with the right scopes. |
| `No Stand-Ups in this window.` | Date range is right but the team didn't run a Stand-Up that day, or you don't have access to it. |
| `Bad time range: --until ... is before --since ...` | Self-explanatory; flip the flags. |
| `File I/O error: ...` | Permissions on `./out/`, full disk, or read-only filesystem. |
| Garbled non-ASCII text in markdown filenames | Filenames are slugged to ASCII; the file body still contains the original UTF-8. |
| Reactions show as `:thumbsup:` instead of 👍 | Some markdown renderers don't auto-substitute shortcodes. Use one that does (e.g., GitHub's renderer) or post-process the file. |

## Project layout

```
src/standup_aggregator/
├── cli.py        Typer app + commands
├── config.py     env loading and validation
├── client.py     httpx Bearer-auth GraphQL client + error hierarchy
├── queries.py    annotated GraphQL strings (start here)
├── timeparse.py  --since/--until → UTC datetimes
├── discover.py   walk teams, page through TeamPromptMeetings
├── fetch.py      hydrate one meeting (responses + replies + reactions)
├── models.py     dataclasses bridging GraphQL → markdown
├── render.py     MeetingDoc → markdown; INDEX.md
├── fs.py         run id, output dir, slugging
└── progress.py   Rich progress + summary table
```

## Tests

```bash
uv run pytest -q
```

The test suite covers the pure helpers (config validation, time parsing, window filtering, slugging, markdown rendering, plaintext extraction, reply-tree construction). End-to-end flows that depend on the live API are verified by running the commands manually — there's no mocked-network test layer.

## License

MIT. (Or as designated by the repository owner.)
