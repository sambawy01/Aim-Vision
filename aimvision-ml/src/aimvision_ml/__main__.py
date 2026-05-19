"""CLI entry-point: `python -m aimvision_ml` and `aimvision-ml` script.

Reports version + which optional extras are importable, so on-call can
diagnose CI vs. dev-laptop install drift without reading the lockfile.
"""

from __future__ import annotations

import importlib.util
from typing import Final

import click
from rich.console import Console
from rich.table import Table

from aimvision_ml import __version__
from aimvision_ml.ingest.cli import ingest

_console = Console()

# Optional extras whose presence we report. None of these are imported here —
# we only check `find_spec` so the light install path stays lazy.
_EXTRAS: Final[dict[str, str]] = {
    "torch": "train",
    "mmpose": "train",
    "mmengine": "train",
    "mmcv": "train",
    "onnxruntime": "infer",
    "coremltools": "coreml",
}


def _extras_status() -> list[tuple[str, str, bool]]:
    return [
        (mod, extra, importlib.util.find_spec(mod) is not None) for mod, extra in _EXTRAS.items()
    ]


@click.group()
@click.version_option(__version__, prog_name="aimvision-ml")
def cli() -> None:
    """AIMVISION ML CLI."""


@cli.command()
def status() -> None:
    """Print version and which optional extras are importable."""
    _console.print(f"[bold]aimvision-ml[/bold] v{__version__}")
    table = Table(title="Optional extras", show_header=True, header_style="bold")
    table.add_column("module")
    table.add_column("extra")
    table.add_column("installed")
    for mod, extra, installed in _extras_status():
        table.add_row(mod, extra, "[green]yes[/green]" if installed else "[dim]no[/dim]")
    _console.print(table)


cli.add_command(ingest)


def main() -> None:
    """Console-script entry point."""
    cli()


if __name__ == "__main__":
    main()
