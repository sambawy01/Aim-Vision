"""VideoMAE-v2 masked-autoencoding pretrain (skeleton).

Heavy — requires --extra train. Cite docs/ml-architecture.md §10
("self-supervised pretraining"). 75% mask ratio, tube masking, 16-frame
clips. Frozen embeddings feed downstream heads.

This script is excluded from CI coverage (pragma: no cover) because it
requires torch + GPU runners.
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
    """Entry point: `python -m aimvision_ml.training.pretrain_videomae`."""
    cfg = yaml.safe_load(Path(config).read_text())
    try:
        import torch  # noqa: F401  (real implementation imports more)
    except ImportError:
        click.echo(
            "torch not installed — install with `uv sync --extra train` on a GPU image.",
            err=True,
        )
        sys.exit(2)
    click.echo(f"[pretrain-videomae] loaded config keys: {list(cfg)}")
    click.echo("[pretrain-videomae] not yet implemented; see docs/ml-architecture.md §10.")
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
