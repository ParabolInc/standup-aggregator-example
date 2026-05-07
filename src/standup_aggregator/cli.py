"""Typer CLI entry point.

Commands are registered here. Implementation lives in sibling modules
so each command body stays small and easy to read.
"""

from __future__ import annotations

import typer
from rich.console import Console

from standup_aggregator import __version__

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
