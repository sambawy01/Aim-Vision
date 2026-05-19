"""ChArUco corner detection + OpenCV calibration seed.

Closes the loop on PR #51's pure-numpy bundle-adjustment scaffold by
adding the *detection* + *initial-seed* stages of the calibration
pipeline. The full production sequence per
`docs/multi-camera-sync-spec.md` §4.2 is:

    1. detect_charuco_corners(image, board)
       — OpenCV ArUco marker detection + Charuco corner interpolation.
    2. seed_calibration_from_detections(detections, board, image_size)
       — OpenCV's calibrateCameraCharuco for an initial guess.
    3. refine_calibration(...)
       — pure-numpy bundle adjustment from `camera_calibration.py`.

OpenCV is an opt-in dependency (`aimvision-ml[vision]` extra). The
import is lazy so the rest of `aimvision_ml` keeps working without
the ~45 MB opencv-python-headless wheel. Modules that need
ChArUco-from-images call into this module; modules that only need
the geometry math stay on the pure-numpy `camera_calibration.py`
surface.

# Why opencv-python-headless

The regular `opencv-python` wheel pulls in GUI subsystem deps (X11,
GTK) that we don't need and that bloat the CI image. The headless
variant ships the same `cv2.*` Python API with the GUI stripped.

# What this module does NOT do

It doesn't ship a marker-detection retry policy, doesn't do
per-image quality scoring beyond OpenCV's `interpolateCornersCharuco`
output, and doesn't drive the multi-camera extrinsic seed step
(stereoCalibrate). Those land alongside real range-capture footage
when the federation rig arrives. This module's job is to make the
detection + single-camera intrinsic seed work end-to-end against
synthetic + real inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from aimvision_ml.inference.camera_calibration import (
    CameraExtrinsics,
    CameraIntrinsics,
    ChArUcoBoard,
)


class OpenCvUnavailableError(RuntimeError):
    """Raised when a function needs cv2 but the `vision` extra isn't
    installed.

    The error message tells the caller exactly what to install. We
    raise eagerly (at first call, not at import) so the rest of the
    inference module still imports cleanly without the extra.
    """


def _require_cv2() -> Any:
    """Lazy-import cv2 and raise a clear error if the `vision` extra
    isn't installed. Returns the `cv2` module — typed as `Any` because
    cv2's own stubs are spotty and the rest of this module accesses
    submodules + attributes dynamically (cv2.aruco, cv2.calibrateCamera,
    cv2.Rodrigues, etc.) for which precise typing buys nothing."""
    try:
        # `import-not-found` fires when cv2 isn't installed (CI default
        # path); `unused-ignore` would fire locally where it is installed.
        # Tagging both lets the same import line stay clean across both.
        import cv2  # type: ignore[import-not-found, unused-ignore]
    except ImportError as exc:  # pragma: no cover - exercised via the dedicated test
        raise OpenCvUnavailableError(
            "ChArUco detection requires the `vision` extra. "
            "Install it with `uv sync --extra vision` "
            "(adds opencv-python-headless to the project venv)."
        ) from exc
    return cv2


# DICT_4X4_100 — OpenCV's CharucoBoard places one ArUco marker in
# every "white" cell of the chessboard pattern, so a squares_x ×
# squares_y board needs at least `squares_x * squares_y / 2` distinct
# markers. The 12 × 9 spec board needs 54 markers, which puts
# DICT_4X4_50 (50 markers) one short and forces the bump to
# DICT_4X4_100. The spec's original "DICT_4X4_50" annotation was off
# by one bracket; the federation-kit print should target 100.
DEFAULT_ARUCO_DICTIONARY_NAME = "DICT_4X4_100"


@dataclass(frozen=True)
class CharucoDetection:
    """Result of `detect_charuco_corners` on a single image.

    `corner_ids[i]` is the internal-corner id (0-indexed in the
    board's flat enumeration) for `corner_positions_px[i]`. Detection
    is partial-occlusion-tolerant — a 12 × 9 board can return as few
    as 4 corners and still be useful as a single-view PnP target.
    `n_detected_markers` is the count of ArUco markers (square-center
    fiducials) that contributed to corner interpolation; a low count
    relative to the board's capacity is the signal for "this image is
    too occluded; skip it."
    """

    corner_positions_px: npt.NDArray[np.float64]
    corner_ids: npt.NDArray[np.int64]
    n_detected_markers: int


def _make_cv2_charuco_board(board: ChArUcoBoard, cv2: Any) -> Any:
    """Build a `cv2.aruco.CharucoBoard` from our `ChArUcoBoard`
    geometry dataclass. The cv2 board takes `(squares_x, squares_y)`
    and the square + marker lengths; we expose the same parameters
    in our dataclass to keep the two surfaces 1:1."""
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, DEFAULT_ARUCO_DICTIONARY_NAME)
    )
    # Marker length = 22 mm per the federation-kit spec; matches the
    # `multi-camera-sync-spec.md` §4.1 description. We keep this
    # ratio (marker = 22/30 ≈ 0.733 of square) consistent regardless
    # of the dataclass's square_length_m setting.
    marker_length_m = board.square_length_m * (22.0 / 30.0)
    return cv2.aruco.CharucoBoard(
        size=(board.squares_x, board.squares_y),
        squareLength=board.square_length_m,
        markerLength=marker_length_m,
        dictionary=dictionary,
    )


def detect_charuco_corners(
    image: npt.NDArray[np.uint8],
    board: ChArUcoBoard,
) -> CharucoDetection:
    """Detect ChArUco internal-corner positions in a single image.

    `image` is HxW (mono) or HxWx3 (BGR) uint8. The OpenCV API works
    on both; if you pass a 3-channel image, it's converted to mono
    internally by the detector. Coordinates returned are pixel-space
    floats (sub-pixel-refined by `interpolateCornersCharuco`).

    Raises `OpenCvUnavailableError` if `aimvision-ml[vision]` isn't
    installed.
    """
    cv2 = _require_cv2()
    if image.dtype != np.uint8:
        raise ValueError(f"image must be uint8; got {image.dtype}")
    if image.ndim not in (2, 3):
        raise ValueError(f"image must be HxW or HxWx3; got shape {image.shape}")

    cv2_board = _make_cv2_charuco_board(board, cv2)
    detector_params = cv2.aruco.DetectorParameters()
    charuco_params = cv2.aruco.CharucoParameters()
    detector = cv2.aruco.CharucoDetector(
        board=cv2_board,
        charucoParams=charuco_params,
        detectorParams=detector_params,
    )

    # `detectBoard` returns (charuco_corners, charuco_ids, marker_corners, marker_ids).
    # Any of them can be None if detection finds nothing.
    charuco_corners, charuco_ids, _marker_corners, marker_ids = detector.detectBoard(image)
    n_markers = 0 if marker_ids is None else int(len(marker_ids))
    if charuco_corners is None or charuco_ids is None:
        return CharucoDetection(
            corner_positions_px=np.zeros((0, 2), dtype=np.float64),
            corner_ids=np.zeros(0, dtype=np.int64),
            n_detected_markers=n_markers,
        )
    # OpenCV returns `(N, 1, 2)`; flatten to `(N, 2)`.
    return CharucoDetection(
        corner_positions_px=charuco_corners.reshape(-1, 2).astype(np.float64),
        corner_ids=charuco_ids.reshape(-1).astype(np.int64),
        n_detected_markers=n_markers,
    )


def seed_calibration_from_detections(
    detections: list[CharucoDetection],
    board: ChArUcoBoard,
    image_size: tuple[int, int],
) -> tuple[CameraIntrinsics, list[CameraExtrinsics], float]:
    """Run OpenCV's `calibrateCameraCharuco` to get an initial guess
    for the bundle-adjustment refinement.

    `image_size` is `(width_px, height_px)` — OpenCV's convention.

    Returns `(intrinsics, per_view_extrinsics, reprojection_rms_px)`.
    The reprojection RMS is OpenCV's overall residual; the caller's
    bundle adjustment (`refine_calibration`) will normally improve on
    it.

    Raises `ValueError` if fewer than 3 views were supplied or if any
    view has fewer than 4 corners (the minimum cv2 accepts).
    """
    cv2 = _require_cv2()
    if len(detections) < 3:
        raise ValueError(f"calibrateCameraCharuco needs at least 3 views; got {len(detections)}")
    for i, d in enumerate(detections):
        if d.corner_positions_px.shape[0] < 4:
            raise ValueError(
                f"view {i} has {d.corner_positions_px.shape[0]} corners; "
                f"calibrateCameraCharuco needs >= 4 per view"
            )

    cv2_board = _make_cv2_charuco_board(board, cv2)

    # OpenCV 4.7+ removed `cv2.aruco.calibrateCameraCharuco`. The
    # replacement is `cv2_board.matchImagePoints(corners, ids)` →
    # `(object_points_3d, image_points_2d)` per view, then
    # `cv2.calibrateCamera(...)` with the lists. This is the
    # documented post-4.7 path; functionally equivalent to the old
    # helper.
    object_points_per_view: list[np.ndarray] = []
    image_points_per_view: list[np.ndarray] = []
    for d in detections:
        corners = d.corner_positions_px.reshape(-1, 1, 2).astype(np.float32)
        ids = d.corner_ids.reshape(-1, 1).astype(np.int32)
        obj_pts, img_pts = cv2_board.matchImagePoints(corners, ids)
        if obj_pts is None or img_pts is None:
            raise ValueError(
                "matchImagePoints returned no matches for a view — "
                "the detection likely has IDs that don't belong to this board"
            )
        object_points_per_view.append(np.asarray(obj_pts, dtype=np.float32))
        image_points_per_view.append(np.asarray(img_pts, dtype=np.float32))

    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objectPoints=object_points_per_view,
        imagePoints=image_points_per_view,
        imageSize=image_size,
        cameraMatrix=None,
        distCoeffs=None,
    )

    # OpenCV returns distortion as (1, 5) or (5, 1) or (1, 4 or 8); the
    # 5-param Brown-Conrady is the standard for the pinhole model so we
    # truncate / pad to exactly 5.
    dist_flat = np.asarray(dist, dtype=np.float64).ravel()
    if dist_flat.size >= 5:
        distortion = dist_flat[:5].copy()
    else:
        distortion = np.zeros(5, dtype=np.float64)
        distortion[: dist_flat.size] = dist_flat

    intrinsics = CameraIntrinsics(
        K=np.asarray(K, dtype=np.float64),
        distortion=distortion,
    )

    extrinsics: list[CameraExtrinsics] = []
    for rvec, tvec in zip(rvecs, tvecs, strict=True):
        # cv2.Rodrigues returns the (R, jacobian) tuple — we want R.
        R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))
        extrinsics.append(
            CameraExtrinsics(
                R=np.asarray(R, dtype=np.float64),
                t=np.asarray(tvec, dtype=np.float64).ravel(),
            )
        )

    return intrinsics, extrinsics, float(rms)


def render_charuco_board_image(
    board: ChArUcoBoard,
    image_size_px: tuple[int, int] = (1600, 1200),
) -> npt.NDArray[np.uint8]:
    """Render a frontal view of the ChArUco board as a uint8 image.

    Exposed for tests + for generating a printable board PDF in
    operator tooling. `image_size_px` is the pixel size of the output
    image (width, height); OpenCV's CharucoBoard.generateImage chooses
    a square pattern that fits.
    """
    cv2 = _require_cv2()
    cv2_board = _make_cv2_charuco_board(board, cv2)
    img = cv2_board.generateImage(image_size_px)
    return np.asarray(img, dtype=np.uint8)


__all__ = [
    "DEFAULT_ARUCO_DICTIONARY_NAME",
    "CharucoDetection",
    "OpenCvUnavailableError",
    "detect_charuco_corners",
    "render_charuco_board_image",
    "seed_calibration_from_detections",
]
