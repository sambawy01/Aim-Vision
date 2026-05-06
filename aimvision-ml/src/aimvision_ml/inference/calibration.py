"""Temperature scaling + conformal prediction sets.

Numpy-only: scalar temperature ``T`` is fit by minimizing NLL on held-out
logits via ``scipy.optimize.minimize_scalar``. Cite Guo et al. 2017 and
docs/ml-architecture.md §8 ("per-task temperature scaling").

Conformal sets follow Angelopoulos & Bates: at calibration time we pick the
score quantile that yields the target coverage on the calibration set; at
test time the prediction set includes every class whose softmax is at
least 1−q after calibration. Implementation deliberately small.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize_scalar


def _softmax(logits: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    out: npt.NDArray[np.float64] = exp / exp.sum(axis=-1, keepdims=True)
    return out


def _nll(probs: npt.NDArray[np.float64], labels: npt.NDArray[np.int64]) -> float:
    eps = 1e-12
    n = probs.shape[0]
    idx = (np.arange(n), labels)
    return float(-np.mean(np.log(probs[idx] + eps)))


@dataclass(frozen=True)
class CalibrationResult:
    """Output of `TemperatureScaler.fit`."""

    temperature: float
    nll_before: float
    nll_after: float


class TemperatureScaler:
    """Single-parameter Platt-style calibration.

    Usage::

        ts = TemperatureScaler()
        result = ts.fit(logits_val, labels_val)
        probs = ts.apply(logits_test)
    """

    def __init__(self) -> None:
        self._temperature: float | None = None

    @property
    def temperature(self) -> float:
        if self._temperature is None:
            raise RuntimeError("TemperatureScaler.fit must be called before .temperature")
        return self._temperature

    def fit(
        self,
        logits: npt.ArrayLike,
        labels: npt.ArrayLike,
        bounds: tuple[float, float] = (0.05, 10.0),
    ) -> CalibrationResult:
        """Fit ``T`` by minimizing NLL on (logits, labels)."""
        logits_arr = np.asarray(logits, dtype=np.float64)
        labels_arr = np.asarray(labels, dtype=np.int64)
        if logits_arr.ndim != 2:
            raise ValueError(f"logits must be (N, C); got {logits_arr.shape}")
        if labels_arr.shape[0] != logits_arr.shape[0]:
            raise ValueError("logits and labels must agree on N")

        nll_before = _nll(_softmax(logits_arr), labels_arr)

        def objective(t: float) -> float:
            if t <= 0:
                return float("inf")
            return _nll(_softmax(logits_arr / t), labels_arr)

        res = minimize_scalar(objective, bounds=bounds, method="bounded")
        if not res.success:
            raise RuntimeError(f"temperature fit did not converge: {res.message}")
        self._temperature = float(res.x)
        nll_after = _nll(_softmax(logits_arr / self._temperature), labels_arr)
        return CalibrationResult(
            temperature=self._temperature,
            nll_before=nll_before,
            nll_after=nll_after,
        )

    def apply(
        self, logits: npt.ArrayLike, temperature: float | None = None
    ) -> npt.NDArray[np.float64]:
        """Return softmaxed probabilities at the fitted (or supplied) ``T``."""
        t = temperature if temperature is not None else self._temperature
        if t is None:
            raise RuntimeError("must fit() or pass an explicit temperature")
        if t <= 0:
            raise ValueError("temperature must be positive")
        return _softmax(np.asarray(logits, dtype=np.float64) / t)


def conformal_prediction_sets(
    probs_cal: npt.ArrayLike,
    labels_cal: npt.ArrayLike,
    probs_test: npt.ArrayLike,
    coverage: float = 0.90,
) -> list[set[int]]:
    """Threshold-based conformal sets at the requested coverage.

    Score s_i = 1 - p_{true}; pick q = the (ceil((n+1)(1-α))/n) quantile,
    test set includes every class with prob >= 1 - q. Plain top-1 fallback
    when N is too small to compute a meaningful quantile.
    """
    probs_cal_arr = np.asarray(probs_cal, dtype=np.float64)
    labels_cal_arr = np.asarray(labels_cal, dtype=np.int64)
    probs_test_arr = np.asarray(probs_test, dtype=np.float64)
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be in (0, 1)")

    n = probs_cal_arr.shape[0]
    if n == 0:
        return [{int(np.argmax(p))} for p in probs_test_arr]

    scores = 1.0 - probs_cal_arr[np.arange(n), labels_cal_arr]
    alpha = 1.0 - coverage
    q_level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    q = float(np.quantile(scores, q_level))
    threshold = 1.0 - q

    out: list[set[int]] = []
    for p in probs_test_arr:
        members = {int(c) for c in np.where(p >= threshold)[0]}
        if not members:
            members = {int(np.argmax(p))}
        out.append(members)
    return out
