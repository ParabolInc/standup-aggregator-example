"""Rich-based progress wrapper used by the `run` command.

Two affordances:

  hydration_progress(total) yields a context manager that wraps a
  Progress instance with one task. Use `advance(...)` per meeting.

  summary_table(...) returns a Rich Table summarizing the run.

Both gracefully no-op when stdout is not a TTY (so CI logs stay tidy).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table


@contextmanager
def hydration_progress(total: int, console: Console):
    if not console.is_terminal:
        # Plain non-TTY mode: yield a no-op object.
        class _Noop:
            def advance(self, *a, **kw): ...
        yield _Noop()
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Hydrating meetings", total=total)

        class _Tracker:
            def advance(self, label: str | None = None) -> None:
                if label:
                    progress.update(task_id, description=label)
                progress.advance(task_id)

        yield _Tracker()


def summary_table(
    *,
    teams_scanned: int,
    meetings: int,
    responses: int,
    replies: int,
    output_dir: Path | None,
) -> Table:
    table = Table(title="Run summary", show_header=False, border_style="green")
    table.add_column(justify="right", style="bold")
    table.add_column()
    table.add_row("Teams scanned", str(teams_scanned))
    table.add_row("Meetings written", str(meetings))
    table.add_row("Responses", str(responses))
    table.add_row("Replies", str(replies))
    table.add_row("Output", str(output_dir) if output_dir else "(dry run, nothing written)")
    return table
