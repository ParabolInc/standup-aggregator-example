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

from standup_aggregator import __version__
from standup_aggregator.client import ParabolApiError, ParabolClient
from standup_aggregator.config import ConfigError, load_config
from standup_aggregator.discover import (
    discover_meetings,
    filter_teams,
    list_visible_teams,
)
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
