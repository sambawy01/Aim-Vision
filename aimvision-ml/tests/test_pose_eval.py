"""Sprint 6 EPIC 6.2: pose evaluation harness.

The trained RTMPose-x is not here yet (GPU-gated). These tests prove
the metric implementation against synthetic poses with known properties:
perfect predictions → PCK = 1.0, large noise → PCK degrades, occluded
predictions don't count.
"""

from __future__ import annotations

import numpy as np
import pytest

from aimvision_ml.eval.pose_eval import (
    COCO_KEYPOINT_SIGMAS,
    COCO_NUM_KEYPOINTS,
    evaluate_pose,
)
from aimvision_ml.eval.synth_pose import SHOOTER_STANCE_GT, make_pose_batch


def test_perfect_prediction_gives_pck_1_and_oks_1() -> None:
    pred, gt = make_pose_batch(8, noise_px=0.0, rng=np.random.default_rng(0))
    report = evaluate_pose(pred, gt)
    assert report.pck_at_0_5 == pytest.approx(1.0)
    assert report.pck_at_0_2 == pytest.approx(1.0)
    assert report.mean_oks == pytest.approx(1.0, abs=1e-6)
    assert report.n_instances == 8


def test_pck_degrades_with_noise() -> None:
    rng = np.random.default_rng(0)
    pred_clean, gt = make_pose_batch(50, noise_px=0.0, rng=rng)
    pred_noisy, _ = make_pose_batch(50, noise_px=15.0, rng=rng)
    clean = evaluate_pose(pred_clean, gt).pck_at_0_5
    noisy = evaluate_pose(pred_noisy, gt).pck_at_0_5
    assert clean == pytest.approx(1.0)
    # With 15px noise vs ~10px head segment, PCK@0.5 must drop noticeably.
    assert noisy < 0.9


def test_occluded_predictions_have_zero_visibility_but_gt_still_counted() -> None:
    """An estimator that marks a keypoint as occluded (vis=0) is *not*
    let off the hook by the eval — the ground-truth visibility decides
    whether the keypoint counts, and the predicted location is still
    checked. This test confirms the implementation: it uses gt_visibility,
    not pred_visibility."""
    pred, gt = make_pose_batch(4, noise_px=0.0, rng=np.random.default_rng(0))
    # Mark all predicted visibilities to 0 — should not affect score.
    pred_occluded = pred.copy()
    pred_occluded[..., 2] = 0.0
    report = evaluate_pose(pred_occluded, gt)
    assert report.pck_at_0_5 == pytest.approx(1.0)


def test_partial_gt_visibility_only_counts_visible_keypoints() -> None:
    """Ground-truth keypoints marked invisible drop out of both the
    numerator and denominator. We mark 5 random GT keypoints invisible
    on a perfect-prediction batch; PCK stays at 1.0 because every
    remaining visible keypoint still matches."""
    rng = np.random.default_rng(7)
    pred, gt = make_pose_batch(4, noise_px=0.0, rng=rng)
    mask = rng.random(gt.shape[:2]) < 0.3
    gt[..., 2] = np.where(mask, 0.0, 1.0)
    report = evaluate_pose(pred, gt)
    assert report.pck_at_0_5 == pytest.approx(1.0)


def test_validate_inputs_rejects_wrong_shape() -> None:
    bad = np.zeros((4, 16, 3), dtype=np.float64)
    gt = np.zeros((4, 17, 3), dtype=np.float64)
    with pytest.raises(ValueError):
        evaluate_pose(bad, gt)


def test_empty_batch_returns_zero_metrics() -> None:
    empty = np.zeros((0, 17, 3), dtype=np.float64)
    report = evaluate_pose(empty, empty)
    assert report.n_instances == 0
    assert report.pck_at_0_5 == 0.0
    assert report.mean_oks == 0.0


def test_per_keypoint_pck_isolates_problem_joints() -> None:
    """Add large noise only to the wrist keypoints; per-keypoint PCK
    should drop for those joints while others stay clean. This is how
    a reviewer drills into a failing PCK number to find the root cause."""
    rng = np.random.default_rng(0)
    pred, gt = make_pose_batch(20, noise_px=0.0, rng=rng)
    wrist_idx = [9, 10]  # left_wrist, right_wrist
    pred[:, wrist_idx, :2] += rng.normal(0.0, 50.0, size=(20, 2, 2))
    report = evaluate_pose(pred, gt)
    other_idx = [i for i in range(COCO_NUM_KEYPOINTS) if i not in wrist_idx]
    assert report.per_keypoint_pck_0_5[other_idx].mean() == pytest.approx(1.0)
    assert report.per_keypoint_pck_0_5[wrist_idx].mean() < 0.5


def test_coco_sigmas_match_published_values() -> None:
    """Spot-check that we haven't drifted from the canonical COCO sigmas.
    These are the exact values from cocoeval.py; any future refactor that
    silently changes a sigma must trip this test."""
    assert COCO_NUM_KEYPOINTS == 17
    assert COCO_KEYPOINT_SIGMAS.shape == (17,)
    assert COCO_KEYPOINT_SIGMAS[0] == pytest.approx(0.026)  # nose
    assert COCO_KEYPOINT_SIGMAS[15] == pytest.approx(0.089)  # left_ankle


def test_shooter_stance_is_within_image_bounds() -> None:
    """If the canonical pose drifts outside reasonable image bounds the
    head-segment fallbacks will hit the bbox-diagonal path. Cheap
    invariant to keep the fixture honest."""
    assert SHOOTER_STANCE_GT.shape == (17, 3)
    assert (SHOOTER_STANCE_GT[:, 0] >= 0).all()
    assert (SHOOTER_STANCE_GT[:, 1] >= 0).all()
    assert (SHOOTER_STANCE_GT[:, 0] <= 400).all()
    assert (SHOOTER_STANCE_GT[:, 1] <= 400).all()
