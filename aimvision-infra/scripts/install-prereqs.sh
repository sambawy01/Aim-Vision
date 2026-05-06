#!/usr/bin/env bash
# =============================================================================
# install-prereqs.sh — install cluster-wide operators that AIMVISION depends on.
#
# Idempotent: safe to re-run. Targets two profiles:
#   ./install-prereqs.sh cloud      → cert-manager, external-secrets, cnpg
#   ./install-prereqs.sh onprem     → cert-manager, sealed-secrets,  cnpg
#   ./install-prereqs.sh dev        → cert-manager, sealed-secrets,  cnpg
#
# Pinned versions live as variables at the top so they're easy to bump in CI.
# =============================================================================

set -euo pipefail

PROFILE="${1:-}"
if [[ -z "${PROFILE}" || "${PROFILE}" != "cloud" && "${PROFILE}" != "onprem" && "${PROFILE}" != "dev" ]]; then
  echo "usage: $0 <cloud|onprem|dev>" >&2
  exit 64
fi

# Pinned versions — bump deliberately.
CNPG_VERSION="0.22.1"
CERT_MANAGER_VERSION="v1.15.3"
SEALED_SECRETS_VERSION="2.16.2"
EXTERNAL_SECRETS_VERSION="0.10.4"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required binary: $1" >&2
    exit 1
  }
}

require helm
require kubectl

log() {
  printf '\033[1;36m==>\033[0m %s\n' "$*"
}

ensure_repo() {
  local name="$1" url="$2"
  if ! helm repo list -o json 2>/dev/null | grep -q "\"$name\""; then
    helm repo add "$name" "$url"
  fi
}

log "Adding Helm repos"
ensure_repo cnpg "https://cloudnative-pg.github.io/charts"
ensure_repo jetstack "https://charts.jetstack.io"
ensure_repo sealed-secrets "https://bitnami-labs.github.io/sealed-secrets"
ensure_repo external-secrets "https://charts.external-secrets.io"
helm repo update

log "Installing cert-manager ${CERT_MANAGER_VERSION}"
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --version "${CERT_MANAGER_VERSION}" \
  --set installCRDs=true \
  --wait --timeout=5m

log "Installing CloudNativePG ${CNPG_VERSION}"
helm upgrade --install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system --create-namespace \
  --version "${CNPG_VERSION}" \
  --wait --timeout=5m

case "$PROFILE" in
  cloud)
    log "Installing external-secrets ${EXTERNAL_SECRETS_VERSION}"
    helm upgrade --install external-secrets external-secrets/external-secrets \
      --namespace external-secrets --create-namespace \
      --version "${EXTERNAL_SECRETS_VERSION}" \
      --set installCRDs=true \
      --wait --timeout=5m
    ;;
  onprem|dev)
    log "Installing sealed-secrets ${SEALED_SECRETS_VERSION}"
    helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
      --namespace kube-system \
      --version "${SEALED_SECRETS_VERSION}" \
      --wait --timeout=5m
    ;;
esac

log "Done. AIMVISION prerequisites installed for profile: ${PROFILE}"
log "Next: helm install aim-${PROFILE} ../helm/aimvision -f ../helm/aimvision/values.yaml -f ../helm/aimvision/values-${PROFILE}.yaml"
