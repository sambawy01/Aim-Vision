#!/usr/bin/env bash
# =============================================================================
# helm-lint.sh — lint the AIMVISION chart against all values overlays.
# Run from the aimvision-infra/ directory or the repo root; both work.
# =============================================================================

set -euo pipefail

CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/helm/aimvision"
cd "$(dirname "${CHART_DIR}")/.."

command -v helm >/dev/null 2>&1 || {
  echo "helm is required" >&2
  exit 1
}

BASE_VALUES="helm/aimvision/values.yaml"
OVERLAYS=(
  "helm/aimvision/values-cloud.yaml"
  "helm/aimvision/values-onprem.yaml"
  "helm/aimvision/values-dev.yaml"
)

# Strict: lint the base, then each overlay merged with base.
echo "==> helm lint (base)"
helm lint "${CHART_DIR}" --strict

for overlay in "${OVERLAYS[@]}"; do
  echo "==> helm lint (base + ${overlay})"
  helm lint "${CHART_DIR}" \
    --strict \
    -f "${BASE_VALUES}" \
    -f "${overlay}"
done

echo "==> all lints passed"
