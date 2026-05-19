"""Tests for `aimvision_ml.inference.charuco_detect`.

Tests are gated on the optional `vision` extra. When opencv-python-
headless isn't installed, the whole module skips silently — CI runs
the default ML container without the extra so these tests don't
block. To run locally:

    uv sync --extra vision
    .venv/bin/pytest tests/test_charuco_detect.py
"""

from __future__ import annotations

import numpy as np
import pytest

# Gate the entire module on cv2 — if it's not installed, every test
# here skips with the standard "could not import" reason.
cv2 = pytest.importorskip("cv2")  # noqa: F841  (used by the imported wrapper)

from aimvision_ml.inference.camera_calibration import (  # noqa: E402
    ChArUcoBoard,
    refine_calibration,
)
from aimvision_ml.inference.charuco_detect import (  # noqa: E402
    CharucoDetection,
    detect_charuco_corners,
    render_charuco_board_image,
    seed_calibration_from_detections,
)

# ----------------------- rendering tests ---------------------------


def test_render_charuco_board_returns_uint8_image_of_requested_size() -> None:
    board = ChArUcoBoard(squares_x=12, squares_y=9, square_length_m=0.030)
    img = render_charuco_board_image(board, image_size_px=(1600, 1200))
    assert img.dtype == np.uint8
    # OpenCV's CharucoBoard.generateImage fits the pattern inside the
    # requested canvas; the returned shape is (h, w), so dimensions
    # are bounded by the requested ones.
    assert img.shape[1] <= 1600
    assert img.shape[0] <= 1200
    # A real ChArUco board has both pure-white and pure-black pixels
    # (chess squares + marker fill). Reject the degenerate "all gray"
    # output that would mean OpenCV's renderer silently no-op'd.
    assert int(img.min()) == 0
    assert int(img.max()) == 255


# ----------------------- detection tests ----------------------------


def test_detect_charuco_on_rendered_frontal_view_recovers_all_corners() -> None:
    """Render the board and detect it back from the same image. Every
    internal corner should be found and the corner-id set should be
    `{0, 1, ..., 87}` for a 12x9 board (88 internal corners)."""
    board = ChArUcoBoard(squares_x=12, squares_y=9, square_length_m=0.030)
    img = render_charuco_board_image(board, image_size_px=(1600, 1200))

    detection = detect_charuco_corners(img, board)
    assert isinstance(detection, CharucoDetection)
    # On a noise-free frontal render every internal corner is visible.
    assert detection.corner_positions_px.shape == (board.num_internal_corners, 2)
    assert detection.corner_ids.shape == (board.num_internal_corners,)
    assert sorted(detection.corner_ids.tolist()) == list(range(board.num_internal_corners))
    # All markers (one per black square minus the corner offsets) get
    # detected on a clean render.
    assert detection.n_detected_markers > 0


def test_detect_charuco_on_blank_image_returns_empty_detection() -> None:
    """No markers, no corners — must come back as a CharucoDetection
    with empty arrays, not raise. (Real range footage will have many
    blank frames between captures; the eval harness mustn't crash.)"""
    board = ChArUcoBoard()
    blank = np.full((1200, 1600), 128, dtype=np.uint8)
    detection = detect_charuco_corners(blank, board)
    assert detection.corner_positions_px.shape == (0, 2)
    assert detection.corner_ids.shape == (0,)
    assert detection.n_detected_markers == 0


def test_detect_charuco_validates_image_dtype_and_shape() -> None:
    board = ChArUcoBoard()
    with pytest.raises(ValueError, match="uint8"):
        detect_charuco_corners(np.zeros((100, 100), dtype=np.float32), board)
    with pytest.raises(ValueError, match="HxW"):
        detect_charuco_corners(np.zeros((100,), dtype=np.uint8), board)
    with pytest.raises(ValueError, match="HxW"):
        detect_charuco_corners(np.zeros((2, 100, 100, 3), dtype=np.uint8), board)


# ----------------------- end-to-end seed → refine tests --------------


def _render_at_pose(
    board: ChArUcoBoard,
    image_size_px: tuple[int, int] = (1600, 1200),
) -> np.ndarray:
    """Wrapper used by tests so the rendered-board canvas size lives
    in one place; OpenCV's CharucoBoard renders in board-frame, so
    the "pose" varies across calls only by the canvas dimensions."""
    return render_charuco_board_image(board, image_size_px=image_size_px)


def test_seed_calibration_requires_at_least_three_views() -> None:
    board = ChArUcoBoard()
    img = _render_at_pose(board)
    detection = detect_charuco_corners(img, board)
    with pytest.raises(ValueError, match="at least 3 views"):
        seed_calibration_from_detections([detection], board, image_size=(1600, 1200))
    with pytest.raises(ValueError, match="at least 3 views"):
        seed_calibration_from_detections([detection, detection], board, image_size=(1600, 1200))


def test_seed_calibration_rejects_views_with_too_few_corners() -> None:
    board = ChArUcoBoard()
    sparse = CharucoDetection(
        corner_positions_px=np.zeros((2, 2), dtype=np.float64),
        corner_ids=np.array([0, 1], dtype=np.int64),
        n_detected_markers=1,
    )
    full = detect_charuco_corners(_render_at_pose(board), board)
    with pytest.raises(ValueError, match=r"view 0 has 2 corners"):
        seed_calibration_from_detections([sparse, full, full], board, image_size=(1600, 1200))


def test_seed_calibration_end_to_end_round_trip() -> None:
    """Render the same frontal board view three times, detect each,
    feed into the seed calibration, then refine with the pure-numpy
    bundle adjustment. The whole pipeline should return without
    raising and produce intrinsics within OpenCV's own residual band.

    Caveat: with three *identical* frontal views OpenCV's intrinsic
    estimate is poorly constrained (no viewpoint diversity → focal
    length unidentified). This test only asserts the seed +
    refinement runs end-to-end, not that the recovered focal length
    is accurate. Real range captures provide the viewpoint diversity
    that the math needs; the synthetic harness can't easily produce
    rotated views of a CharucoBoard.generateImage() output."""
    board = ChArUcoBoard()
    img = _render_at_pose(board)
    detection = detect_charuco_corners(img, board)
    detections = [detection, detection, detection]

    intrinsics, extrinsics, rms = seed_calibration_from_detections(
        detections, board, image_size=(1600, 1200)
    )
    # OpenCV's reported RMS on a clean synthetic should be a fraction
    # of a pixel.
    assert rms < 5.0, f"unexpected reprojection rms: {rms}"
    assert intrinsics.K.shape == (3, 3)
    assert intrinsics.distortion.shape == (5,)
    assert len(extrinsics) == 3

    # Hand the seed into the bundle-adjustment refinement. Use the
    # board's internal corners as the world points; pad-extract the
    # corners observed in this single-view detection (all 88) for each
    # view since the synthetic detection saw all of them.
    world_points = board.corner_points_3d()
    observations = [detection.corner_positions_px for _ in detections]
    result = refine_calibration(world_points, observations, intrinsics, extrinsics)
    # The refinement returns successfully — the assertion is on the
    # *pipeline*, not the geometric accuracy (which the synthetic
    # frontal-only views can't credibly bound).
    assert result.iterations >= 1
    assert result.reprojection_error_px_p95 >= 0.0
