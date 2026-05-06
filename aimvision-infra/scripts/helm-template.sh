#!/usr/bin/env bash
# =============================================================================
# helm-template.sh — render the chart for review. Outputs to /tmp/aimvision-*.yaml
# =============================================================================

set -euo pipefail

CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/helm/aimvision"
cd "$(dirname "${CHART_DIR}")/.."

command -v helm >/dev/null 2>&1 || {
  echo "helm is required" >&2
  exit 1
}

render() {
  local profile="$1"
  local out="/tmp/aimvision-${profile}.yaml"
  echo "==> rendering profile=${profile} -> ${out}"
  helm template "aim-${profile}" "${CHART_DIR}" \
    -f "helm/aimvision/values.yaml" \
    -f "helm/aimvision/values-${profile}.yaml" \
    --namespace aimvision \
    >"${out}"
  echo "    bytes=$(wc -c <"${out}") resources=$(grep -c '^kind:' "${out}" || true)"
}

render cloud
render onprem
render dev

echo "==> done. Inspect the rendered output with:"
echo "    less /tmp/aimvision-cloud.yaml"
echo "    less /tmp/aimvision-onprem.yaml"
echo "    less /tmp/aimvision-dev.yaml"
