# aimvision-ml

Model training, evaluation, ONNX export, and registry for AIMVISION.

This repo is the source of truth for:

- The diagnostic taxonomy code (mirrors `docs/diagnostic-taxonomy.md`).
- Calibrated multi-task heads (per `docs/ml-architecture.md` §8).
- Stratified evaluation + bias-audit gates (per `docs/ml-architecture.md` §12).
- ONNX export configs for RTMPose-Lite, YOLOv8n barrel, diagnostic MLP.
- LLM coaching-notes JSON Schema validation, PII stripping, and verifier.
- Sample-provenance tracking + the right-to-erasure exclusion list.

## Layout

See `docs/ml-architecture.md` for the architectural rationale. The directory
layout follows the train/eval/inference/registry split from §10–§13.

## Setup

```bash
uv sync                                # light deps only (numpy/scipy/pydantic/...)
uv sync --extra dev --extra infer      # CI-equivalent install
uv sync --group train                  # heavy: torch + torchvision + openmim
uv run mim install "mmengine>=0.10" "mmcv>=2.1" "mmpose>=1.3"
                                       # OpenMMLab stack (GPU image only)
uv sync --group coreml                 # macOS + coremltools (model conversion)
```

The default install brings only the deps used by tests, eval gates, schema
validation, and exclusion-list bookkeeping. Training scripts are skeletons
that import `torch` / `mmpose` / `mmcv` lazily; running them requires the
heavy `train` group plus the post-sync `mim install` step.

`train` and `coreml` are PEP 735 dependency-groups (not extras) so uv's
universal-lock resolution does not try to build torch from sdist on CPU-only
CI runners. The OpenMMLab stack (mmcv, mmengine, mmpose) is installed via
`mim` because their sdists don't play well with uv's build isolation; this
is the OpenMMLab-recommended install path.

## Day-one commands

```bash
make test         # pytest -v on the lightweight modules
make lint         # ruff check + ruff format --check
make typecheck    # mypy src
```

## Heavy-stack commands (require --group train)

```bash
make train-pose          # RTMPose-Lite distillation
make eval-diagnostic     # stratified eval + bias-audit gate
make export-onnx         # ONNX + INT8 quantization for live-tier models
```

## CLI

```bash
uv run aimvision-ml --help
uv run aimvision-ml status      # prints version + which extras are available
```

## CI

`.github/workflows/ml-ci.yml` (at the monorepo root) runs `dev + infer` on
push to anything in `aimvision-ml/**`. Training-extra jobs run separately on
GPU runners and are not part of the merge gate.

## References

- `docs/ml-architecture.md` — full ML architecture (sensor stack, live tier,
  post-session tier, longitudinal tier, training strategy, registry).
- `docs/diagnostic-taxonomy.md` — the diagnostic atoms; `taxonomy.py` mirrors
  this and the canonical tokens get re-pinned at the Sprint 9 lock.
- `docs/llm-coaching-notes-schema.md` — the JSON Schema the LLM emits via
  grammar-constrained decoding; `llm/schema.py` loads it from this markdown.
- `docs/performance-budgets.md` — latency/battery/thermal budgets the live
  tier ONNX exports must satisfy.
