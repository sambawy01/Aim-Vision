"""Per-athlete LoRA adapter trainer (skeleton).

Heavy — requires --extra train. Cite docs/ml-architecture.md §10
(per-athlete LoRA personalization, rank 8, alpha 16, applied to the
diagnostic heads only after ~200 shots). Adapter is athlete-private; the
base model is shared.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml


@click.command()  # pragma: no cover
@click.option("--config", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--athlete-id", required=True, help="Athlete UUID; consent must be on file.")
@click.option("--shot-count", type=int, default=200, show_default=True)
def main(config: str, athlete_id: str, shot_count: int) -> None:  # pragma: no cover
    cfg = yaml.safe_load(Path(config).read_text())
    try:
        import torch  # noqa: F401
    except ImportError:
        click.echo("torch not installed — install with `uv sync --extra train`.", err=True)
        sys.exit(2)
    if shot_count < 200:
        click.echo(
            f"[lora-per-athlete] insufficient shots ({shot_count} < 200); skipping.", err=True
        )
        sys.exit(3)
    click.echo(f"[lora-per-athlete] athlete={athlete_id} shots={shot_count} cfg={list(cfg)}")
    click.echo("[lora-per-athlete] not yet implemented; see docs/ml-architecture.md §10.")
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
