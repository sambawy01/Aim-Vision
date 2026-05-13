"""Synthetic pose generator — Sprint 6 EPIC 6.2.

Generates COCO-17 keypoint instances with controllable noise so the eval
harness can be exercised without a real annotated dataset. The pose used
is a stylized "shooter stance" — feet shoulder-width apart, both hands
near eye level, head upright — which is the only stance class the live
tier sees.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

COCO_NUM_KEYPOINTS = 17

# A single canonical shooter-stance pose in image coordinates. Roughly a
# 200-pixel tall figure standing in the center of a 400x400 image.
SHOOTER_STANCE_GT: npt.NDArray[np.float64] = np.array(
    [
        # (x, y, visibility=1) for each of the 17 COCO keypoints
        (200, 80, 1.0),  # 0  nose
        (195, 78, 1.0),  # 1  left_eye
        (205, 78, 1.0),  # 2  right_eye
        (188, 82, 1.0),  # 3  left_ear
        (212, 82, 1.0),  # 4  right_ear
        (175, 120, 1.0),  # 5  left_shoulder
        (225, 120, 1.0),  # 6  right_shoulder
        (160, 100, 1.0),  # 7  left_elbow  (raised, gun mount)
        (240, 100, 1.0),  # 8  right_elbow (raised, gun mount)
        (175, 95, 1.0),  # 9  left_wrist  (near cheek/stock)
        (225, 95, 1.0),  # 10 right_wrist (trigger hand)
        (180, 200, 1.0),  # 11 left_hip
        (220, 200, 1.0),  # 12 right_hip
        (175, 270, 1.0),  # 13 left_knee
        (225, 270, 1.0),  # 14 right_knee
        (170, 340, 1.0),  # 15 left_ankle
        (230, 340, 1.0),  # 16 right_ankle
    ],
    dtype=np.float64,
)


def make_pose_batch(
    n_instances: int,
    *,
    noise_px: float = 0.0,
    occlusion_rate: float = 0.0,
    rng: np.random.Generator | None = None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Returns (predicted, ground_truth) batches of shape (N, 17, 3).

    Each ground-truth instance is the canonical shooter stance with a
    random ±20px shift so the batch is not literally identical rows. The
    predicted instances add isotropic Gaussian noise with stddev
    `noise_px` pixels on the (x, y) coords, then optionally mark
    `occlusion_rate` fraction of *predicted* visibilities as 0 — this is
    how a real estimator handles low-confidence joints.
    """
    if rng is None:
        rng = np.random.default_rng(0)
    if n_instances < 0:
        raise ValueError("n_instances must be >= 0")

    gt = np.broadcast_to(SHOOTER_STANCE_GT, (n_instances, COCO_NUM_KEYPOINTS, 3)).copy()
    shifts = rng.uniform(-20, 20, size=(n_instances, 1, 2))
    gt[..., :2] += shifts

    pred = gt.copy()
    if noise_px > 0:
        noise = rng.normal(0.0, noise_px, size=(n_instances, COCO_NUM_KEYPOINTS, 2))
        pred[..., :2] += noise

    if occlusion_rate > 0:
        mask = rng.random((n_instances, COCO_NUM_KEYPOINTS)) < occlusion_rate
        pred[..., 2] = np.where(mask, 0.0, 1.0)

    return pred, gt
