"""ONNX export with INT8 quantization for RTMPose-Lite.

Heavy — requires --extra train + --extra infer. Cite
docs/performance-budgets.md §4 for per-device latency budgets and
ml-architecture.md §3 for the macro-F1 loss tolerance (≤ 1 point).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml


@click.command()  # pragma: no cover
@click.option("--config", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--out", type=click.Path(dir_okay=False), default=None)
def main(config: str, out: str | None) -> None:  # pragma: no cover
    cfg = yaml.safe_load(Path(config).read_text())
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        click.echo("onnxruntime not installed — install with `uv sync --extra infer`.", err=True)
        sys.exit(2)
    click.echo(f"[onnx-rtmpose] export config: {list(cfg.get('export', {}))}")
    click.echo("[onnx-rtmpose] not yet implemented; see docs/performance-budgets.md §4.")
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
