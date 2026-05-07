"""Typer CLI entry point.

Commands are registered here. Implementation lives in sibling modules
so each command body stays small and easy to read.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from standup_aggregator import __version__
from standup_aggregator.client import ParabolApiError, ParabolClient
from standup_aggregator.config import ConfigError, load_config
from standup_aggregator.queries import VIEWER_QUERY

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
