# aimvision-ml Makefile
# All targets assume `uv sync` has run with the appropriate extras.

PY := uv run

.PHONY: help
help:
	@echo "Targets:"
	@echo "  lint              ruff check + ruff format --check"
	@echo "  typecheck         mypy src"
	@echo "  test              pytest -v on lightweight modules"
	@echo "  train-pose        RTMPose-Lite distillation (requires --group train)"
	@echo "  train-diagnostic  multi-task diagnostic head (requires --group train)"
	@echo "  pretrain-videomae VideoMAE-v2 masked-autoencoding pretrain (requires --group train)"
	@echo "  eval-diagnostic   stratified eval + bias-audit gate"
	@echo "  export-onnx       ONNX + INT8 export for live-tier models (requires --extra infer)"
	@echo "  status            print version and lib status"

.PHONY: lint
lint:
	$(PY) ruff check src tests
	$(PY) ruff format --check src tests

.PHONY: format
format:
	$(PY) ruff format src tests
	$(PY) ruff check --fix src tests

.PHONY: typecheck
typecheck:
	$(PY) mypy src

.PHONY: test
test:
	$(PY) pytest -v

.PHONY: status
status:
	$(PY) python -m aimvision_ml status

.PHONY: train-pose
train-pose:
	$(PY) python -m aimvision_ml.training.train_pose \
		--config configs/rtmpose_lite/mobile.yaml

.PHONY: train-diagnostic
train-diagnostic:
	$(PY) python -m aimvision_ml.training.train_diagnostic \
		--config configs/diagnostic_head/base.yaml

.PHONY: pretrain-videomae
pretrain-videomae:
	$(PY) python -m aimvision_ml.training.pretrain_videomae \
		--config configs/videomae_pretrain/v1.yaml

.PHONY: eval-diagnostic
eval-diagnostic:
	$(PY) python -m aimvision_ml.eval.gates \
		--config configs/diagnostic_head/base.yaml

.PHONY: export-onnx
export-onnx:
	$(PY) python -m aimvision_ml.export.onnx_rtmpose \
		--config configs/rtmpose_lite/mobile.yaml
	$(PY) python -m aimvision_ml.export.onnx_diagnostic \
		--config configs/diagnostic_head/base.yaml
