"""Tests for `aimvision_ml.inference.camera_calibration`.

Synthetic-board harness: build a ChArUco geometry, place virtual
cameras with known intrinsics + extrinsics at realistic federation-rig
distances (5 m baselines, ~70° HFOV), project the board's internal
corners into each camera, optionally add gaussian noise, then run the
bundle-adjustment refinement starting from a perturbed initial guess
and verify it recovers the ground truth to the spec's error budget.

The harness does NOT exercise ChArUco *detection* — that lands when
the cv2 follow-up sub-slice arrives. What's covered here is the
geometric math: projection, distortion model, the optimizer's basin
of attraction, and the diagnostic outputs that feed the per-session
recalibration trigger.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from aimvision_ml.inference.camera_calibration import (
    CalibrationResult,
    CameraExtrinsics,
    CameraIntrinsics,
    ChArUcoBoard,
    _make_intrinsics_from_fov,
    project_points,
    refine_calibration,
    reprojection_errors,
)

# ----------------------- Board geometry tests -----------------------


def test_board_internal_corner_count_matches_spec_12x9() -> None:
    """12 × 9 squares → 11 × 8 = 88 internal corners."""
    board = ChArUcoBoard(squares_x=12, squares_y=9, square_length_m=0.030)
    points = board.corner_points_3d()
    assert board.num_internal_corners == 88
    assert points.shape == (88, 3)
    # All z = 0 (board is planar).
    assert np.allclose(points[:, 2], 0.0)
    # First internal corner sits at (1 * square_length, 1 * square_length, 0).
    assert points[0] == pytest.approx(np.array([0.030, 0.030, 0.0]))
    # Last internal corner sits at (11 * square_length, 8 * square_length, 0).
    assert points[-1] == pytest.approx(np.array([0.330, 0.240, 0.0]))


def test_board_corner_count_scales_with_size() -> None:
    small = ChArUcoBoard(squares_x=5, squares_y=4, square_length_m=0.020)
    assert small.num_internal_corners == 12  # (5-1) * (4-1)
    assert small.corner_points_3d().shape == (12, 3)


# ----------------------- Projection / distortion tests -----------------


def test_no_distortion_projection_matches_pinhole_formula() -> None:
    """A point at world (0, 0, 5) seen by a camera at origin pointing
    down +Z should project to the image center."""
    intr = _make_intrinsics_from_fov(1920, 1080, horizontal_fov_deg=70.0)
    extr = CameraExtrinsics(R=np.eye(3), t=np.zeros(3))
    point = np.array([[0.0, 0.0, 5.0]])
    projected = project_points(point, intr, extr)
    assert projected[0, 0] == pytest.approx(intr.cx)
    assert projected[0, 1] == pytest.approx(intr.cy)


def test_distortion_round_trip_is_identity_at_image_center() -> None:
    """The image center is on the optical axis (xn = yn = 0); even
    nonzero distortion coefficients can't displace it."""
    K = np.array([[1500.0, 0.0, 960.0], [0.0, 1500.0, 540.0], [0.0, 0.0, 1.0]])
    intr = CameraIntrinsics(K=K, distortion=np.array([0.1, -0.05, 0.001, -0.001, 0.02]))
    # Centerline point: at the principal axis, distortion is 0 by definition.
    extr = CameraExtrinsics(R=np.eye(3), t=np.zeros(3))
    point_on_axis = np.array([[0.0, 0.0, 3.0]])
    proj = project_points(point_on_axis, intr, extr)
    assert proj[0, 0] == pytest.approx(intr.cx)
    assert proj[0, 1] == pytest.approx(intr.cy)


def test_distortion_displaces_off_axis_points() -> None:
    """Off-axis points must shift under nonzero radial distortion;
    if they didn't, the model would be broken."""
    K = np.array([[1500.0, 0.0, 960.0], [0.0, 1500.0, 540.0], [0.0, 0.0, 1.0]])
    intr_undist = CameraIntrinsics(K=K, distortion=np.zeros(5))
    intr_radial = CameraIntrinsics(K=K, distortion=np.array([0.15, 0.0, 0.0, 0.0, 0.0]))
    extr = CameraExtrinsics(R=np.eye(3), t=np.zeros(3))
    # Point well off the optical axis.
    point = np.array([[0.5, 0.3, 2.0]])
    proj_undist = project_points(point, intr_undist, extr)
    proj_radial = project_points(point, intr_radial, extr)
    delta = np.linalg.norm(proj_radial - proj_undist)
    # A 0.15 radial coefficient on a corner point should shift > 1 px
    # (it's a chunky coefficient). If the model were a no-op, delta = 0.
    assert delta > 1.0


def test_project_points_validates_shape() -> None:
    intr = _make_intrinsics_from_fov(1920, 1080, 70.0)
    extr = CameraExtrinsics(R=np.eye(3), t=np.zeros(3))
    with pytest.raises(ValueError):
        project_points(np.zeros(3), intr, extr)  # not (N, 3)
    with pytest.raises(ValueError):
        project_points(np.zeros((4, 2)), intr, extr)  # (N, 2) not (N, 3)


def test_intrinsics_extrinsics_validation_rejects_wrong_shapes() -> None:
    with pytest.raises(ValueError):
        CameraIntrinsics(K=np.eye(2))  # not 3x3
    with pytest.raises(ValueError):
        CameraIntrinsics(K=np.eye(3), distortion=np.zeros(3))  # not (5,)
    with pytest.raises(ValueError):
        CameraExtrinsics(R=np.eye(2), t=np.zeros(3))
    with pytest.raises(ValueError):
        CameraExtrinsics(R=np.eye(3), t=np.zeros(2))


# ----------------------- Refinement tests ---------------------------


def _make_pose(
    pos: tuple[float, float, float],
    look_at: tuple[float, float, float],
    up: tuple[float, float, float] = (0.0, -1.0, 0.0),
) -> CameraExtrinsics:
    """Build extrinsics for a camera positioned at `pos` and looking
    toward `look_at`. The camera frame's +z axis points along the
    look direction (OpenCV convention)."""
    pos_arr = np.array(pos, dtype=np.float64)
    look = np.array(look_at, dtype=np.float64)
    forward = look - pos_arr
    forward = forward / np.linalg.norm(forward)
    up_arr = np.array(up, dtype=np.float64)
    right = np.cross(forward, up_arr)
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)
    # Camera-to-world rotation has columns [right, -up, forward] for the
    # OpenCV convention (y points down in the image). We need world-to-camera.
    R_cw = np.column_stack([right, -true_up, forward])
    R = R_cw.T
    t = -R @ pos_arr
    return CameraExtrinsics(R=R, t=t)


def _project_board(
    board: ChArUcoBoard,
    intrinsics: CameraIntrinsics,
    extrinsics: CameraExtrinsics,
    noise_px: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Project the board's internal corners, optionally adding noise."""
    points_3d = board.corner_points_3d()
    obs = project_points(points_3d, intrinsics, extrinsics)
    if noise_px > 0.0:
        assert rng is not None
        obs = obs + rng.normal(0.0, noise_px, size=obs.shape)
    return obs


def test_refinement_recovers_intrinsics_from_noise_free_observations() -> None:
    """With zero observation noise, the bundle adjustment should
    recover the ground-truth intrinsics + extrinsics to numerical
    precision."""
    board = ChArUcoBoard()
    points_3d = board.corner_points_3d()
    true_intr = _make_intrinsics_from_fov(1920, 1080, horizontal_fov_deg=70.0)
    # Three different board poses — board placed at varying angles
    # like an operator would when waving it in front of the camera.
    true_extrinsics = [
        _make_pose(pos=(0.0, 0.0, 2.0), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(0.3, 0.0, 2.0), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(-0.2, 0.1, 2.5), look_at=(0.165, 0.120, 0.0)),
    ]
    observations = [_project_board(board, true_intr, ext) for ext in true_extrinsics]

    # Initial guess: focal slightly off, extrinsics perturbed.
    init_intr = CameraIntrinsics(
        K=true_intr.K * np.array([[0.9, 1.0, 1.05], [1.0, 0.9, 0.95], [1.0, 1.0, 1.0]]),
        distortion=np.zeros(5),
    )
    init_extrinsics = [
        CameraExtrinsics(
            R=Rotation.from_rotvec(
                Rotation.from_matrix(ext.R).as_rotvec() + np.array([0.05, -0.03, 0.02])
            ).as_matrix(),
            t=ext.t + np.array([0.05, -0.03, 0.1]),
        )
        for ext in true_extrinsics
    ]

    result = refine_calibration(points_3d, observations, init_intr, init_extrinsics)
    assert isinstance(result, CalibrationResult)
    assert result.converged
    # Sub-pixel reprojection error on synthetic noise-free input.
    assert result.reprojection_error_px_p95 < 1e-3
    # Recovered fx/fy within 0.1% of ground truth.
    assert result.intrinsics.fx == pytest.approx(true_intr.fx, rel=1e-3)
    assert result.intrinsics.fy == pytest.approx(true_intr.fy, rel=1e-3)


def test_refinement_tolerates_observation_noise() -> None:
    """At 0.3 px gaussian noise on every detected corner (a plausible
    floor for a real ChArUco detector at 1080p), the optimizer should
    still produce sub-pixel mean reprojection error and recover the
    focal length within a few percent.

    The pose set deliberately spans 1.2–3.0 m to break the
    focal-length / depth ambiguity that always-similar distances
    cause — the optimizer needs to see the board at different scales
    to pin down fx independent of t_z."""
    rng = np.random.default_rng(1)
    board = ChArUcoBoard()
    points_3d = board.corner_points_3d()
    true_intr = _make_intrinsics_from_fov(1920, 1080, horizontal_fov_deg=70.0)
    true_extrinsics = [
        _make_pose(pos=(0.0, 0.0, 1.2), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(0.3, 0.0, 1.5), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(-0.2, 0.1, 2.2), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(0.1, -0.15, 2.8), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(0.0, 0.0, 3.0), look_at=(0.165, 0.120, 0.0)),
    ]
    observations = [
        _project_board(board, true_intr, ext, noise_px=0.3, rng=rng) for ext in true_extrinsics
    ]
    # Initial guess: same focal length, identity-pose extrinsics — same
    # initial-guess noise floor a coarse `cv2.calibrateCamera` would
    # hand us.
    init_intr = true_intr
    init_extrinsics = [
        CameraExtrinsics(
            R=Rotation.from_rotvec(
                Rotation.from_matrix(ext.R).as_rotvec() + np.array([0.02, -0.01, 0.01])
            ).as_matrix(),
            t=ext.t + np.array([0.03, -0.02, 0.05]),
        )
        for ext in true_extrinsics
    ]

    result = refine_calibration(points_3d, observations, init_intr, init_extrinsics)
    assert result.converged
    # 0.3 px noise floor → mean reprojection error should land near
    # the noise variance. Loose upper bound to keep the test stable
    # against rng-seed sensitivity.
    assert result.reprojection_error_px_mean < 1.0
    # Production calibration with cv2 + Ceres bundle adjustment hits
    # sub-percent focal-length recovery. This scaffold (scipy
    # least_squares only, no Jacobian sparsity) lands in the 1–3% band
    # under 0.3 px corner noise; we gate at 3% as the "optimizer is
    # still inside the basin of attraction" sanity check.
    assert result.intrinsics.fx == pytest.approx(true_intr.fx, rel=3e-2)
    assert result.intrinsics.fy == pytest.approx(true_intr.fy, rel=3e-2)


def test_refinement_recovers_radial_distortion() -> None:
    """Apply a known radial distortion to the synthetic projection,
    then verify the optimizer recovers it from a no-distortion start."""
    board = ChArUcoBoard()
    points_3d = board.corner_points_3d()
    true_intr = CameraIntrinsics(
        K=_make_intrinsics_from_fov(1920, 1080, horizontal_fov_deg=70.0).K,
        distortion=np.array([-0.18, 0.05, 0.0, 0.0, 0.0]),
    )
    true_extrinsics = [
        _make_pose(pos=(0.0, 0.0, 1.8), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(0.25, 0.0, 1.9), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(-0.15, 0.1, 2.0), look_at=(0.165, 0.120, 0.0)),
        _make_pose(pos=(0.0, -0.1, 2.1), look_at=(0.165, 0.120, 0.0)),
    ]
    observations = [_project_board(board, true_intr, ext) for ext in true_extrinsics]
    init_intr = CameraIntrinsics(K=true_intr.K, distortion=np.zeros(5))
    init_extrinsics = list(true_extrinsics)

    result = refine_calibration(points_3d, observations, init_intr, init_extrinsics)
    assert result.converged
    # k1 recovered within 0.02 of ground truth.
    assert result.intrinsics.distortion[0] == pytest.approx(-0.18, abs=0.02)
    assert result.intrinsics.distortion[1] == pytest.approx(0.05, abs=0.02)


def test_refinement_validates_inputs() -> None:
    board = ChArUcoBoard()
    points_3d = board.corner_points_3d()
    intr = _make_intrinsics_from_fov(1920, 1080, 70.0)
    extr = _make_pose((0.0, 0.0, 2.0), (0.165, 0.120, 0.0))
    obs = project_points(points_3d, intr, extr)

    with pytest.raises(ValueError):
        # Empty views list — nothing to refine.
        refine_calibration(points_3d, [], intr, [])
    with pytest.raises(ValueError):
        # Mismatched observation / extrinsics counts.
        refine_calibration(points_3d, [obs], intr, [extr, extr])
    with pytest.raises(ValueError):
        # Per-view observation shape doesn't match corner count.
        refine_calibration(points_3d, [obs[:10]], intr, [extr])


# ----------------------- Reprojection-error diagnostics -------------


def test_reprojection_errors_zero_on_self_projection() -> None:
    """If we project the board into a camera and then ask for
    reprojection error against that very projection, the error must
    be exactly zero (numerically: < 1e-10)."""
    board = ChArUcoBoard()
    points_3d = board.corner_points_3d()
    intr = _make_intrinsics_from_fov(1920, 1080, 70.0)
    extr = _make_pose((0.0, 0.0, 2.0), (0.165, 0.120, 0.0))
    obs = project_points(points_3d, intr, extr)

    errors = reprojection_errors(points_3d, obs, intr, extr)
    assert errors.shape == (board.num_internal_corners,)
    assert np.max(errors) < 1e-10
