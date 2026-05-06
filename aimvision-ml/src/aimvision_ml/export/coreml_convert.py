"""Core ML conversion via coremltools (declared dep, not run in CI).

Heavy — requires --extra coreml. Cite docs/performance-budgets.md §4
(Apple Neural Engine acceleration on iPhone 13+ devices).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click


@click.command()  # pragma: no cover
@click.option("--onnx-in", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--out", type=click.Path(dir_okay=False), required=True)
@click.option(
    "--compute-units", type=click.Choice(["all", "cpu_and_ne", "cpu_only"]), default="cpu_and_ne"
)
def main(onnx_in: str, out: str, compute_units: str) -> None:  # pragma: no cover
    try:
        import coremltools  # noqa: F401
    except ImportError:
        click.echo("coremltools not installed — install with `uv sync --extra coreml`.", err=True)
        sys.exit(2)
    click.echo(f"[coreml-convert] {onnx_in} → {out} (compute_units={compute_units})")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    click.echo("[coreml-convert] not yet implemented.")
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
