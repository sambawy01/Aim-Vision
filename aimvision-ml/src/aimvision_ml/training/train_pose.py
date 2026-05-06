"""RTMPose-Lite distillation entry (skeleton).

Heavy — requires --extra train. Cite docs/ml-architecture.md §4.
Distill RTMPose-x (Wholebody-133) → RTMPose-Lite (COCO-17) on our own
data. Live tier consumes only signals the COCO topology supports.
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
        import mmpose  # noqa: F401
    except ImportError:
        click.echo("mmpose not installed — install with `uv sync --extra train`.", err=True)
        sys.exit(2)
    click.echo(f"[train-pose] teacher={cfg.get('teacher', {}).get('arch')!r}")
    click.echo("[train-pose] not yet implemented; see docs/ml-architecture.md §4.")
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
