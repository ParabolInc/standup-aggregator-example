# standup-aggregator

A small Python CLI that extracts [Parabol](https://parabol.co) Stand-Up data (TeamPromptMeetings) for a date range and writes it to markdown files.

This codebase doubles as a **demonstrator for Parabol Personal Access Tokens (PATs)**: the GraphQL queries are annotated, the auth flow is plain and visible, and the README explains how Parabol's API works.

## Quick start

### 1. Install

```bash
uv sync
```

### 2. Mint a Personal Access Token

1. Sign in to [Parabol](https://action.parabol.co).
2. Visit **Profile → Personal Access Tokens** (`/me/profile/personal-access-tokens`).
3. Click **Create token**.
4. Required scopes for this CLI:
   - `MEETINGS_READ` — to read meetings, prompts, and responses.
   - `COMMENTS_READ` — to read reply threads on each response.
5. Copy the token (begins with `pat_`). You will only see it once.

### 3. Configure your environment

```bash
cp .env.example .env
# Open .env and paste your PAT into PARABOL_PAT=...
```

### 4. Verify it works

```bash
uv run standup-aggregator doctor
```

You should see a green "Parabol PAT — OK" panel with your name and a table of teams the PAT can see.

## How the API works

- **Endpoint:** `https://action.parabol.co/graphql` (POST). For self-hosted instances, set `PARABOL_BASE_URL`.
- **Auth header:** `Authorization: Bearer pat_<token>`.
- **Errors:** Parabol generally returns HTTP 200 with an `errors` array in the body even when something went wrong. The client surfaces the first message verbatim.

More commands will be wired up as later sprints land. See `docs/superpowers/plans/2026-05-07-standup-aggregator.md`.
