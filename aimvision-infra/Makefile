# =============================================================================
# AIMVISION infra — Makefile
# =============================================================================
# Targets:
#   make help                  # this text
#   make install-prereqs-cloud # cert-manager, ESO, CNPG (cluster-wide)
#   make install-prereqs-onprem
#   make install-prereqs-dev
#   make helm-lint             # strict lint against every overlay
#   make helm-template-cloud   # render -> /tmp/aimvision-cloud.yaml
#   make helm-template-onprem
#   make helm-template-dev
#   make install-cloud         # helm upgrade --install with the cloud overlay
#   make install-onprem
#   make install-dev
# =============================================================================

CHART := helm/aimvision
NAMESPACE ?= aimvision

.DEFAULT_GOAL := help

.PHONY: help
help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-32s\033[0m %s\n", $$1, $$2}'

# -----------------------------------------------------------------------------
# Prereqs
# -----------------------------------------------------------------------------

.PHONY: install-prereqs-cloud
install-prereqs-cloud: ## Install cluster-wide operators for the cloud profile
	./scripts/install-prereqs.sh cloud

.PHONY: install-prereqs-onprem
install-prereqs-onprem: ## Install cluster-wide operators for the on-prem profile
	./scripts/install-prereqs.sh onprem

.PHONY: install-prereqs-dev
install-prereqs-dev: ## Install cluster-wide operators for the dev profile
	./scripts/install-prereqs.sh dev

# -----------------------------------------------------------------------------
# Lint / render
# -----------------------------------------------------------------------------

.PHONY: helm-lint
helm-lint: ## helm lint against every overlay (strict)
	helm lint $(CHART) --strict
	helm lint $(CHART) --strict -f $(CHART)/values.yaml -f $(CHART)/values-cloud.yaml
	helm lint $(CHART) --strict -f $(CHART)/values.yaml -f $(CHART)/values-onprem.yaml
	helm lint $(CHART) --strict -f $(CHART)/values.yaml -f $(CHART)/values-dev.yaml

.PHONY: helm-template-cloud
helm-template-cloud: ## Render the cloud overlay to /tmp/aimvision-cloud.yaml
	helm template aim-cloud $(CHART) \
	  -f $(CHART)/values.yaml -f $(CHART)/values-cloud.yaml \
	  --namespace $(NAMESPACE) > /tmp/aimvision-cloud.yaml
	@echo "wrote /tmp/aimvision-cloud.yaml"

.PHONY: helm-template-onprem
helm-template-onprem: ## Render the on-prem overlay to /tmp/aimvision-onprem.yaml
	helm template aim-onprem $(CHART) \
	  -f $(CHART)/values.yaml -f $(CHART)/values-onprem.yaml \
	  --namespace $(NAMESPACE) > /tmp/aimvision-onprem.yaml
	@echo "wrote /tmp/aimvision-onprem.yaml"

.PHONY: helm-template-dev
helm-template-dev: ## Render the dev overlay to /tmp/aimvision-dev.yaml
	helm template aim-dev $(CHART) \
	  -f $(CHART)/values.yaml -f $(CHART)/values-dev.yaml \
	  --namespace $(NAMESPACE) > /tmp/aimvision-dev.yaml
	@echo "wrote /tmp/aimvision-dev.yaml"

# -----------------------------------------------------------------------------
# Install / upgrade
# -----------------------------------------------------------------------------

.PHONY: install-cloud
install-cloud: ## helm upgrade --install for the cloud profile
	helm upgrade --install aim-cloud $(CHART) \
	  -f $(CHART)/values.yaml -f $(CHART)/values-cloud.yaml \
	  --namespace $(NAMESPACE) --create-namespace \
	  --wait --timeout=10m

.PHONY: install-onprem
install-onprem: ## helm upgrade --install for the on-prem profile
	helm upgrade --install aim-onprem $(CHART) \
	  -f $(CHART)/values.yaml -f $(CHART)/values-onprem.yaml \
	  --namespace $(NAMESPACE) --create-namespace \
	  --wait --timeout=10m

.PHONY: install-dev
install-dev: ## helm upgrade --install for the dev profile
	helm upgrade --install aim-dev $(CHART) \
	  -f $(CHART)/values.yaml -f $(CHART)/values-dev.yaml \
	  --namespace $(NAMESPACE) --create-namespace \
	  --wait --timeout=10m

.PHONY: test
test: ## helm test on the most recent install
	helm test -n $(NAMESPACE) aim-dev || helm test -n $(NAMESPACE) aim-onprem || helm test -n $(NAMESPACE) aim-cloud
