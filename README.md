# standup-aggregator

A small Python CLI that extracts [Parabol](https://parabol.co) Stand-Up data (TeamPromptMeetings) for a date range and writes it to markdown files.

This codebase doubles as a **demonstrator for Parabol Personal Access Tokens (PATs)**: the GraphQL queries are annotated, the auth flow is plain and visible, and the README explains how Parabol's API works.

## Status

Under construction. See `docs/superpowers/plans/2026-05-07-standup-aggregator.md` for the implementation plan.

## Quick start

```bash
uv sync
cp .env.example .env   # then add your PARABOL_PAT
uv run standup-aggregator --help
```

## License

MIT (or as designated by the repo owner).
