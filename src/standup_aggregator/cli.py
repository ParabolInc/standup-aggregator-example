"""Typer CLI entry point.

Commands are registered here. Implementation lives in sibling modules
so each command body stays small and easy to read.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from standup_aggregator import __version__
from standup_aggregator.client import ParabolApiError, ParabolClient
from standup_aggregator.config import ConfigError, load_config
from standup_aggregator.discover import (
    discover_meetings,
    filter_teams,
    list_visible_teams,
)
from standup_aggregator.fetch import fetch_meeting
from standup_aggregator.fs import make_run_dir, mint_run_id
from standup_aggregator.models import MeetingDoc, Reply
from standup_aggregator.queries import VIEWER_QUERY
from standup_aggregator.render import render_index, render_meeting, render_meeting_filename
from standup_aggregator.timeparse import TimeParseError, parse_window

app = typer.Typer(
    name="standup-aggregator",
    help="Extract Parabol Stand-Up data to markdown.",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"standup-aggregator [bold cyan]{__version__}[/]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Standup Aggregator — Parabol Stand-Up extractor."""


@app.command()
def doctor() -> None:
    """Verify your Parabol PAT and list teams it can see."""
    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[red bold]Config error:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[dim]Calling[/] [cyan]{cfg.graphql_url}[/]")
    try:
        with ParabolClient(cfg) as client:
            data = client.query(VIEWER_QUERY)
    except ParabolApiError as exc:
        console.print(f"[red bold]API error:[/] {exc}")
        raise typer.Exit(code=1)

    viewer = data.get("viewer") or {}
    name = viewer.get("preferredName") or "(no name)"
    email = viewer.get("email") or "(no email)"
    teams = viewer.get("teams") or []

    summary = f"[bold cyan]{name}[/]\n[dim]{email}[/]\n\n{len(teams)} team(s) visible to this PAT."
    console.print(Panel(summary, title="Parabol PAT — OK", border_style="green"))

    if teams:
        table = Table(title="Teams", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name")
        for t in teams:
            table.add_row(t.get("id", ""), t.get("name", ""))
        console.print(table)


@app.command("list")
def list_cmd(
    since: str | None = typer.Option(
        None,
        "--since",
        help="Window start. ISO date, ISO datetime, 'today', 'yesterday', or 'Nd'/'Nw'.",
    ),
    until: str | None = typer.Option(
        None,
        "--until",
        help="Window end. Same formats as --since. Defaults to now.",
    ),
    teams: list[str] = typer.Option(
        [],
        "--team",
        help="Filter to one or more teams by id or display name. Repeatable.",
    ),
) -> None:
    """List Stand-Ups in the given window without fetching responses."""
    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[red bold]Config error:[/] {exc}")
        raise typer.Exit(code=1)

    try:
        since_dt, until_dt, desc = parse_window(since, until, now=datetime.now(tz=timezone.utc))
    except TimeParseError as exc:
        console.print(f"[red bold]Bad time range:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[dim]Window:[/] {desc}")

    try:
        with ParabolClient(cfg) as client:
            visible_teams = list_visible_teams(client)
            chosen_teams = filter_teams(visible_teams, teams)
            if not chosen_teams:
                console.print("[yellow]No teams matched the filter.[/]")
                raise typer.Exit(code=0)
            meetings = discover_meetings(client, chosen_teams, since_dt, until_dt)
    except ParabolApiError as exc:
        console.print(f"[red bold]API error:[/] {exc}")
        raise typer.Exit(code=1)

    if not meetings:
        console.print("[yellow]No Stand-Ups found in this window.[/]")
        raise typer.Exit(code=0)

    table = Table(title=f"Stand-Ups ({len(meetings)})", show_header=True, header_style="bold magenta")
    table.add_column("Team", style="cyan")
    table.add_column("Name")
    table.add_column("Created (UTC)", style="dim")
    table.add_column("Responses", justify="right")
    table.add_column("ID", style="dim")

    meetings.sort(key=lambda m: m.created_at, reverse=True)
    for m in meetings:
        table.add_row(
            m.team_name,
            m.name,
            m.created_at.strftime("%Y-%m-%d %H:%M"),
            str(m.response_count),
            m.id,
        )
    console.print(table)


def _render_replies_tree(replies: list[Reply], parent: Tree) -> None:
    for r in replies:
        if r.plaintext:
            label = f"[bold]{escape(r.author_name)}[/]: {escape(r.plaintext)}"
        else:
            label = f"[bold]{escape(r.author_name)}[/]: [dim](empty)[/]"
        node = parent.add(label)
        if r.children:
            _render_replies_tree(r.children, node)


def _print_meeting(doc: MeetingDoc) -> None:
    header = (
        f"[bold cyan]{escape(doc.name)}[/]  ·  [magenta]{escape(doc.team_name)}[/]\n"
        f"[dim]{doc.created_at.strftime('%Y-%m-%d %H:%M UTC')}[/]\n\n"
        f"[italic]Prompt:[/] {escape(doc.prompt) if doc.prompt else '(no prompt)'}\n"
        f"[dim]{doc.response_count} response(s)[/]"
    )
    console.print(Panel(header, border_style="cyan"))

    for resp in doc.responses:
        rxn = (
            "  ".join(f"{escape(r.emoji_id)}×{r.count}" for r in resp.reactions)
            or "[dim]no reactions[/]"
        )
        if resp.plaintext:
            plaintext_line = escape(resp.plaintext)
        else:
            plaintext_line = "[dim](empty)[/]"
        body = (
            f"[bold]{escape(resp.author_name)}[/]  [dim]{resp.created_at.strftime('%Y-%m-%d %H:%M')}[/]\n\n"
            f"{plaintext_line}\n\n"
            f"{rxn}"
        )
        console.print(Panel(body, border_style="green"))

        if resp.replies:
            tree = Tree("[bold]Replies[/]")
            _render_replies_tree(resp.replies, tree)
            console.print(tree)


@app.command()
def inspect(meeting_id: str = typer.Argument(..., help="The meeting id to hydrate.")) -> None:
    """Hydrate one meeting and pretty-print it to the terminal."""
    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[red bold]Config error:[/] {exc}")
        raise typer.Exit(code=1)

    try:
        with ParabolClient(cfg) as client:
            doc = fetch_meeting(client, meeting_id)
    except ParabolApiError as exc:
        console.print(f"[red bold]API error:[/] {exc}")
        raise typer.Exit(code=1)
    except ValueError as exc:
        console.print(f"[red bold]Not found:[/] {exc}")
        raise typer.Exit(code=1)

    _print_meeting(doc)


@app.command()
def run(
    since: str | None = typer.Option(None, "--since", help="Window start."),
    until: str | None = typer.Option(None, "--until", help="Window end."),
    teams: list[str] = typer.Option([], "--team", help="Filter to teams (id or name). Repeatable."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Discover and render in memory; skip writes."),
) -> None:
    """Discover Stand-Ups in the window and render them to ./out/<run-id>/."""
    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[red bold]Config error:[/] {exc}")
        raise typer.Exit(code=1)

    try:
        since_dt, until_dt, desc = parse_window(since, until, now=datetime.now(tz=timezone.utc))
    except TimeParseError as exc:
        console.print(f"[red bold]Bad time range:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[dim]Window:[/] {desc}")

    try:
        with ParabolClient(cfg) as client:
            visible_teams = list_visible_teams(client)
            chosen_teams = filter_teams(visible_teams, teams)
            if not chosen_teams:
                console.print("[yellow]No teams matched the filter.[/]")
                raise typer.Exit(code=0)

            console.print(f"[dim]Teams:[/] {', '.join(t['name'] for t in chosen_teams)}")
            summaries = discover_meetings(client, chosen_teams, since_dt, until_dt)
            if not summaries:
                console.print("[yellow]No Stand-Ups in this window.[/]")
                raise typer.Exit(code=0)

            console.print(f"[green]Found {len(summaries)} meeting(s). Hydrating...[/]")

            docs = []
            for s in summaries:
                console.print(f"  • {s.team_name} — {s.name} ({s.id})")
                docs.append(fetch_meeting(client, s.id))
    except ParabolApiError as exc:
        console.print(f"[red bold]API error:[/] {exc}")
        raise typer.Exit(code=1)

    run_id = mint_run_id(datetime.now(tz=timezone.utc))
    if dry_run:
        console.print(f"[cyan]--dry-run:[/] would have written {len(docs)} file(s) to out/{run_id}/")
        for doc in docs:
            console.print(f"  • {render_meeting_filename(doc)}")
        return

    try:
        out_dir = make_run_dir(run_id)
        rendered: list[tuple] = []
        for doc in docs:
            filename = render_meeting_filename(doc)
            (out_dir / filename).write_text(render_meeting(doc), encoding="utf-8")
            rendered.append((doc, filename))
        (out_dir / "INDEX.md").write_text(render_index(rendered), encoding="utf-8")
    except OSError as exc:
        console.print(f"[red bold]File I/O error:[/] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[green bold]Wrote {len(rendered)} file(s) + INDEX.md to[/] [cyan]{out_dir}/[/]")
