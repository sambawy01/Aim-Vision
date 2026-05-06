"""Diagnostic head training script (skeleton).

Heavy — requires --extra train. Cite docs/ml-architecture.md §8.
Per-task temperature scaling is fit on a held-out set after training
(see `inference.calibration.TemperatureScaler`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml


@click.command()  # pragma: no cover
@click.option("--config", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--resume", type=click.Path(dir_okay=False), default=None)
def main(config: str, resume: str | None) -> None:  # pragma: no cover
    cfg = yaml.safe_load(Path(config).read_text())
    try:
        import torch  # noqa: F401
    except ImportError:
        click.echo("torch not installed — install with `uv sync --extra train`.", err=True)
        sys.exit(2)
    click.echo(f"[train-diagnostic] loaded config: branches={list(cfg.get('branches', {}))}")
    click.echo("[train-diagnostic] not yet implemented; see docs/ml-architecture.md §8.")
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
