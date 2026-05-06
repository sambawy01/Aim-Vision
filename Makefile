# =============================================================================
# AIMVISION monorepo — top-level Makefile
# =============================================================================
# Delegates to per-subrepo Makefiles where they exist. Keep this file thin —
# each subrepo owns its own build/test invariants. The top-level Makefile is
# a convenience layer for "do it everywhere" workflows.
#
# Usage:
#   make help
#   make setup          # one-time: install pre-commit, hooks, deps in each subrepo
#   make test-all       # run every subrepo's tests
#   make lint-all       # run every subrepo's linter
#   make helm-lint      # AIMVISION chart lint, every overlay
#   make precommit      # pre-commit run --all-files
#   make format-all     # format every subrepo
# =============================================================================

SHELL := /usr/bin/env bash

# Subrepos — order matters only for parallel build dependencies (none today).
SUBREPOS := aimvision-backend aimvision-camera-core aimvision-mobile aimvision-web aimvision-ml aimvision-infra

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# -----------------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------------

.PHONY: setup
setup: ## Install pre-commit, hooks, and per-subrepo deps
	@command -v pre-commit >/dev/null 2>&1 || pip install --user pre-commit==3.8.0
	pre-commit install
	pre-commit install --hook-type commit-msg
	@for d in $(SUBREPOS); do \
	  if [ -f "$$d/Makefile" ]; then \
	    echo "==> $$d: setup"; \
	    $(MAKE) -C "$$d" setup || echo "(no setup target in $$d)"; \
	  fi; \
	done

# -----------------------------------------------------------------------------
# Repo-wide checks
# -----------------------------------------------------------------------------

.PHONY: precommit
precommit: ## Run all pre-commit hooks across the whole tree
	pre-commit run --all-files --show-diff-on-failure

.PHONY: gitleaks
gitleaks: ## Scan the whole tree for committed secrets
	@command -v gitleaks >/dev/null 2>&1 || { echo "gitleaks not installed (brew install gitleaks)"; exit 1; }
	gitleaks detect --no-banner --redact --source .

.PHONY: helm-lint
helm-lint: ## Lint the AIMVISION Helm chart against every overlay
	$(MAKE) -C aimvision-infra helm-lint

# -----------------------------------------------------------------------------
# Fan-out to subrepos
# -----------------------------------------------------------------------------

.PHONY: lint-all
lint-all: ## Run lint in every subrepo that defines one
	@set -e; for d in $(SUBREPOS); do \
	  if [ -f "$$d/Makefile" ]; then \
	    echo "==> $$d: lint"; \
	    $(MAKE) -C "$$d" lint || exit $$?; \
	  fi; \
	done

.PHONY: test-all
test-all: ## Run tests in every subrepo that defines them
	@set -e; for d in $(SUBREPOS); do \
	  if [ -f "$$d/Makefile" ]; then \
	    echo "==> $$d: test"; \
	    $(MAKE) -C "$$d" test || exit $$?; \
	  fi; \
	done

.PHONY: format-all
format-all: ## Run formatters in every subrepo that defines one
	@for d in $(SUBREPOS); do \
	  if [ -f "$$d/Makefile" ]; then \
	    echo "==> $$d: format"; \
	    $(MAKE) -C "$$d" format || echo "(no format target in $$d)"; \
	  fi; \
	done

# -----------------------------------------------------------------------------
# Convenience wrappers
# -----------------------------------------------------------------------------

.PHONY: ci-local
ci-local: precommit lint-all test-all helm-lint ## Mimic CI locally

.PHONY: clean
clean: ## Clean per-subrepo build artifacts
	@for d in $(SUBREPOS); do \
	  if [ -f "$$d/Makefile" ]; then \
	    echo "==> $$d: clean"; \
	    $(MAKE) -C "$$d" clean || true; \
	  fi; \
	done
