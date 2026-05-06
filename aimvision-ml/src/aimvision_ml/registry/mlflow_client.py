"""MLflow tracking + Model Registry wrapper.

Cite docs/ml-architecture.md §13. Every prediction in the database carries
a `model_version` column forever — this is how we attribute regressions
and run retros. The wrapper exists so callers don't sprinkle MLflow API
calls across the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    pass


@dataclass(frozen=True)
class ModelVersionRef:
    """Reference to a registered model version. Stable across registry backends."""

    name: str
    version: str
    stage: str  # "Staging" | "Production" | "Archived" | "None"
    run_id: str
    metrics: dict[str, float]


class MLflowRegistry:
    """Thin wrapper over the MLflow Tracking + Registry APIs."""

    def __init__(self, tracking_uri: str) -> None:
        self.tracking_uri = tracking_uri

    def _client(self) -> Any:  # local import: mlflow is installed by default
        import mlflow

        mlflow.set_tracking_uri(self.tracking_uri)
        from mlflow.tracking import MlflowClient

        return MlflowClient(tracking_uri=self.tracking_uri)

    def get_production(self, name: str) -> ModelVersionRef:
        """Return the current Production version for a model name."""
        client = self._client()
        versions = client.get_latest_versions(name, stages=["Production"])
        if not versions:
            raise LookupError(f"no Production version registered for {name!r}")
        v = versions[0]
        run = client.get_run(v.run_id)
        return ModelVersionRef(
            name=v.name,
            version=v.version,
            stage=v.current_stage,
            run_id=v.run_id,
            metrics={k: float(val) for k, val in run.data.metrics.items()},
        )

    def promote(self, name: str, version: str, *, archive_existing: bool = True) -> None:
        """Promote a version to Production. Cite ml-architecture.md §13."""
        client = self._client()
        client.transition_model_version_stage(
            name=name,
            version=version,
            stage="Production",
            archive_existing_versions=archive_existing,
        )

    def rollback(self, name: str, target_version: str) -> None:
        """Single-flag rollback per ml-architecture.md §13.

        Promotes ``target_version`` and archives the rest. Tested
        quarterly per the same section.
        """
        self.promote(name, target_version, archive_existing=True)
