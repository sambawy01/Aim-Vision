"""Pose estimator evaluation — Sprint 6 EPIC 6.2.

Two metrics that the upcoming RTMPose-x training must beat:

  PCK@k : Percentage of Correct Keypoints. A keypoint is correct if its
          predicted location is within `k * head_segment_length` of the
          ground truth. Standard pose-estimation metric; the `head_segment`
          normalization makes the threshold scale-invariant. PCK@0.5 is
          the usual quality bar.

  OKS   : Object Keypoint Similarity, COCO-style. Per-keypoint Gaussian
          likelihood scaled by the object area + per-joint visibility
          weight. mAP@OKS is what COCO publishes; here we expose the
          per-instance OKS and let `gates.py` aggregate.

This module is numpy-only — no torch, no openmim. Designed so the CI
gate can evaluate any export (ONNX, torch, or even the classical
detector) by feeding in arrays of predicted vs. ground-truth keypoints.

Sprint 6 ships the eval *scaffolding*; the trained RTMPose-x lands in a
follow-up once the GPU comes online. Until then the test path exercises
the metric implementation against synthetic poses with known noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

COCO_NUM_KEYPOINTS = 17

# COCO sigmas (per-keypoint stddev for OKS). Source: cocoeval.py;
# replicated here so we do not pull pycocotools at eval time.
COCO_KEYPOINT_SIGMAS: npt.NDArray[np.float64] = np.array(
    [
        0.026,  # nose
        0.025,  # left_eye
        0.025,  # right_eye
        0.035,  # left_ear
        0.035,  # right_ear
        0.079,  # left_shoulder
        0.079,  # right_shoulder
        0.072,  # left_elbow
        0.072,  # right_elbow
        0.062,  # left_wrist
        0.062,  # right_wrist
        0.107,  # left_hip
        0.107,  # right_hip
        0.087,  # left_knee
        0.087,  # right_knee
        0.089,  # left_ankle
        0.089,  # right_ankle
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class PoseEvalReport:
    pck_at_0_5: float
    pck_at_0_2: float
    """Mean Object Keypoint Similarity across instances (0..1, higher better)."""
    mean_oks: float
    """Per-keypoint accuracy at PCK@0.5. Shape (17,)."""
    per_keypoint_pck_0_5: npt.NDArray[np.float64]
    n_instances: int


def _validate_pose_inputs(
    pred: npt.NDArray[np.float64],
    gt: npt.NDArray[np.float64],
) -> None:
    if pred.shape != gt.shape:
        raise ValueError(f"pred {pred.shape} and gt {gt.shape} must match")
    if pred.ndim != 3 or pred.shape[1] != COCO_NUM_KEYPOINTS:
        raise ValueError(f"expected (N, {COCO_NUM_KEYPOINTS}, 3) shaped arrays, got {pred.shape}")
    if pred.shape[2] != 3:
        raise ValueError("third axis must be (x, y, visibility/score)")


def _head_segment_length(gt_instance: npt.NDArray[np.float64]) -> float:
    """Diagonal between the two eyes (kp 1, 2). Falls back to the
    shoulder-to-shoulder distance if eyes are not annotated."""
    left_eye, right_eye = gt_instance[1], gt_instance[2]
    if left_eye[2] > 0 and right_eye[2] > 0:
        diag = float(np.linalg.norm(left_eye[:2] - right_eye[:2]))
        if diag > 0:
            return diag
    left_sh, right_sh = gt_instance[5], gt_instance[6]
    if left_sh[2] > 0 and right_sh[2] > 0:
        diag = float(np.linalg.norm(left_sh[:2] - right_sh[:2]))
        if diag > 0:
            return diag
    # Last resort — bounding-box diagonal of visible keypoints.
    visible = gt_instance[gt_instance[:, 2] > 0, :2]
    if visible.size == 0:
        return 1.0
    return float(np.linalg.norm(visible.max(axis=0) - visible.min(axis=0))) or 1.0


def _instance_area(gt_instance: npt.NDArray[np.float64]) -> float:
    """Bounding-box area over visible keypoints. Used as the OKS scale."""
    visible = gt_instance[gt_instance[:, 2] > 0, :2]
    if visible.size == 0:
        return 1.0
    extent = visible.max(axis=0) - visible.min(axis=0)
    area = float(extent[0] * extent[1])
    return max(area, 1.0)


def evaluate_pose(
    pred_keypoints: npt.ArrayLike,
    gt_keypoints: npt.ArrayLike,
    *,
    pck_thresholds: tuple[float, ...] = (0.5, 0.2),
) -> PoseEvalReport:
    """Compute PCK@0.5, PCK@0.2, and mean OKS over a batch of instances.

    Inputs are shape ``(N, 17, 3)`` with columns ``(x, y, visibility)``.
    Visibility 0 means the keypoint is unlabelled; it contributes neither
    to the numerator nor the denominator.
    """
    pred = np.asarray(pred_keypoints, dtype=np.float64)
    gt = np.asarray(gt_keypoints, dtype=np.float64)
    _validate_pose_inputs(pred, gt)
    n = pred.shape[0]
    if n == 0:
        return PoseEvalReport(
            pck_at_0_5=0.0,
            pck_at_0_2=0.0,
            mean_oks=0.0,
            per_keypoint_pck_0_5=np.zeros(COCO_NUM_KEYPOINTS, dtype=np.float64),
            n_instances=0,
        )

    correct_at = {thr: np.zeros(COCO_NUM_KEYPOINTS, dtype=np.float64) for thr in pck_thresholds}
    visible_count = np.zeros(COCO_NUM_KEYPOINTS, dtype=np.float64)
    oks_per_instance = np.zeros(n, dtype=np.float64)

    for i in range(n):
        head = _head_segment_length(gt[i])
        area = _instance_area(gt[i])
        diffs = np.linalg.norm(pred[i, :, :2] - gt[i, :, :2], axis=1)
        v = gt[i, :, 2] > 0
        visible_count += v.astype(np.float64)
        for thr in pck_thresholds:
            within = (diffs <= thr * head) & v
            correct_at[thr] += within.astype(np.float64)

        # OKS = sum_v exp(-d^2 / (2 * s^2 * k^2)) / count(visible)
        # s = sqrt(area), k = COCO sigma.
        s = np.sqrt(area)
        k = COCO_KEYPOINT_SIGMAS
        e = -(diffs**2) / (2.0 * (s**2) * (k**2) + 1e-12)
        oks = np.exp(e)
        oks_masked = oks * v
        denom = max(float(v.sum()), 1.0)
        oks_per_instance[i] = float(oks_masked.sum() / denom)

    per_kp_pck_05 = np.where(
        visible_count > 0,
        correct_at[0.5] / np.maximum(visible_count, 1.0),
        0.0,
    )
    total_visible = float(visible_count.sum())
    pck_05 = float(correct_at[0.5].sum() / total_visible) if total_visible > 0 else 0.0
    pck_02 = float(correct_at[0.2].sum() / total_visible) if total_visible > 0 else 0.0

    return PoseEvalReport(
        pck_at_0_5=pck_05,
        pck_at_0_2=pck_02,
        mean_oks=float(oks_per_instance.mean()),
        per_keypoint_pck_0_5=per_kp_pck_05,
        n_instances=n,
    )
