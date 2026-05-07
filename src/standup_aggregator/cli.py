"""Typer CLI entry point.

Commands are registered here. Implementation lives in sibling modules
so each command body stays small and easy to read.
"""

from __future__ import annotations

from datetime import datetime, timezone

import typer
from rich.console import Console
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
from standup_aggregator.models import MeetingDoc, Reply
from standup_aggregator.queries import VIEWER_QUERY
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
        node = parent.add(f"[bold]{r.author_name}[/]: {r.plaintext or '[dim](empty)[/]'}")
        if r.children:
            _render_replies_tree(r.children, node)


def _print_meeting(doc: MeetingDoc) -> None:
    header = (
        f"[bold cyan]{doc.name}[/]  ·  [magenta]{doc.team_name}[/]\n"
        f"[dim]{doc.created_at.strftime('%Y-%m-%d %H:%M UTC')}[/]\n\n"
        f"[italic]Prompt:[/] {doc.prompt or '(no prompt)'}\n"
        f"[dim]{doc.response_count} response(s)[/]"
    )
    console.print(Panel(header, border_style="cyan"))

    for resp in doc.responses:
        rxn = (
            "  ".join(f"{r.emoji_id}×{r.count}" for r in resp.reactions)
            or "[dim]no reactions[/]"
        )
        body = (
            f"[bold]{resp.author_name}[/]  [dim]{resp.created_at.strftime('%Y-%m-%d %H:%M')}[/]\n\n"
            f"{resp.plaintext or '[dim](empty)[/]'}\n\n"
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
