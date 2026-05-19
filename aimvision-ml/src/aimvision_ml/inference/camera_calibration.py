"""Multi-camera geometric calibration scaffold (Sprint 5 EPIC 5.4).

Implements the math layer of `docs/multi-camera-sync-spec.md` §4:
ChArUco-board geometry, the pinhole + Brown-Conrady projection model,
per-camera intrinsic refinement, and the bundle-adjustment joint
refinement across multiple views.

# What this module is

Pure numpy + scipy. The math is unit-testable against synthetic boards
without any image-IO dependency, so CI catches regressions in the
geometric reasoning without us having to ship opencv-python in the
default ML extras.

# What this module is NOT (yet)

It does NOT do ChArUco *detection*. The production path is OpenCV's
`cv2.aruco.detectMarkers` + `cv2.aruco.interpolateCornersCharuco`,
followed by `cv2.calibrateCameraCharucoExtended` to seed the
optimizer here. That step needs `opencv-python` which we keep as an
optional extra (~100 MB binary, GPU-irrelevant) to keep the default
ML container small. When the federation rig is bench-ready and we
need real-image calibration, the follow-up slice adds the `vision`
extra and a thin wrapper that runs detection → seeds this module's
bundle adjustment.

What we *do* ship here:

- `ChArUcoBoard` — 3D geometry of the 12×9 board from the spec.
- `CameraIntrinsics` / `CameraExtrinsics` — the calibrated parameter
  surface. Layout matches the `CameraCalibration` Rust struct in spec
  §4.5.
- `project_points` — pinhole + Brown-Conrady 5-parameter distortion.
- `reprojection_errors` — per-point error vector for diagnostics and
  for the optimizer's residual function.
- `refine_calibration` — joint refinement of intrinsics + extrinsics
  across an arbitrary number of views via `scipy.optimize.least_squares`
  on the reprojection residual. Uses Rodrigues' 3-vector
  parameterization for rotations (no quaternion-norm constraint to
  enforce; the optimizer stays unconstrained).

# Coordinate conventions

- World frame: ChArUco board's top-left internal corner is the origin;
  +x along the long axis of the board, +y down the short axis,
  +z out of the board plane toward the camera.
- Camera frame: pinhole standard; +x right in image, +y down in image,
  +z forward into the scene (so positive Z is in front of the camera).
- Pixel frame: origin at the top-left, +x right, +y down, in pixels.

Intrinsic matrix `K`:

    [fx  0  cx]
    [ 0  fy cy]
    [ 0  0   1]

Distortion `(k1, k2, p1, p2, k3)` — Brown-Conrady, matching OpenCV's
`distortion_coeffs` order.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import numpy.typing as npt
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class ChArUcoBoard:
    """3D geometry of a ChArUco board.

    The board's internal corners (the chessboard intersections that
    survive partial marker occlusion) are the calibration targets.
    For an `squares_x` × `squares_y` board there are
    `(squares_x - 1) * (squares_y - 1)` internal corners.

    Spec default per multi-camera-sync-spec.md §4.1: 12 × 9 squares,
    30 mm square length. Adjust per-rig as needed.
    """

    squares_x: int = 12
    squares_y: int = 9
    square_length_m: float = 0.030

    @property
    def num_internal_corners(self) -> int:
        return (self.squares_x - 1) * (self.squares_y - 1)

    def corner_points_3d(self) -> npt.NDArray[np.float64]:
        """`(N, 3)` array of internal-corner 3D positions on the board
        plane (z = 0). Row order matches OpenCV's row-major top-left
        origin convention so a real `interpolateCornersCharuco`
        output can be paired with this directly."""
        xs = np.arange(1, self.squares_x) * self.square_length_m
        ys = np.arange(1, self.squares_y) * self.square_length_m
        grid_y, grid_x = np.meshgrid(ys, xs, indexing="ij")
        points = np.stack(
            [grid_x.ravel(), grid_y.ravel(), np.zeros(grid_x.size)],
            axis=1,
        )
        return points.astype(np.float64)


@dataclass(frozen=True)
class CameraIntrinsics:
    """3×3 intrinsic matrix + 5-parameter Brown-Conrady distortion.

    Matches the `CameraCalibration.intrinsics_K` + `.distortion_coeffs`
    fields in the per-session schema from spec §4.5.
    """

    K: npt.NDArray[np.float64]
    distortion: npt.NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(5, dtype=np.float64)
    )

    def __post_init__(self) -> None:
        if self.K.shape != (3, 3):
            raise ValueError(f"K must be 3x3; got {self.K.shape}")
        if self.distortion.shape != (5,):
            raise ValueError(f"distortion must be (5,); got {self.distortion.shape}")

    @property
    def fx(self) -> float:
        return float(self.K[0, 0])

    @property
    def fy(self) -> float:
        return float(self.K[1, 1])

    @property
    def cx(self) -> float:
        return float(self.K[0, 2])

    @property
    def cy(self) -> float:
        return float(self.K[1, 2])


@dataclass(frozen=True)
class CameraExtrinsics:
    """Rotation + translation taking world points into the camera frame.

    A world point `P_w` maps to camera frame via `P_c = R @ P_w + t`.
    For the multi-camera rig, extrinsics are stored relative to
    camera 0 — see spec §4.5.
    """

    R: npt.NDArray[np.float64]
    t: npt.NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.R.shape != (3, 3):
            raise ValueError(f"R must be 3x3; got {self.R.shape}")
        if self.t.shape != (3,):
            raise ValueError(f"t must be (3,); got {self.t.shape}")


@dataclass(frozen=True)
class CalibrationResult:
    """Outcome of `refine_calibration`.

    `extrinsics` is one entry per input view (camera × pose). The
    `reprojection_error_px_p95` field is what gets persisted into the
    per-session `CameraCalibration` row from spec §4.5.
    """

    intrinsics: CameraIntrinsics
    extrinsics: tuple[CameraExtrinsics, ...]
    reprojection_error_px_p95: float
    reprojection_error_px_mean: float
    iterations: int
    converged: bool


def _apply_distortion(
    xn: npt.NDArray[np.float64],
    yn: npt.NDArray[np.float64],
    distortion: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Brown-Conrady 5-parameter distortion on normalized image coords.

    Implements the same formulation as OpenCV's pinhole model so the
    distortion coefficients carry the same meaning across the
    detection (OpenCV) and refinement (this module) paths.
    """
    k1, k2, p1, p2, k3 = distortion
    r2 = xn * xn + yn * yn
    radial = 1.0 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    x_dist = xn * radial + 2.0 * p1 * xn * yn + p2 * (r2 + 2.0 * xn * xn)
    y_dist = yn * radial + p1 * (r2 + 2.0 * yn * yn) + 2.0 * p2 * xn * yn
    return x_dist, y_dist


def project_points(
    points_world: npt.NDArray[np.float64],
    intrinsics: CameraIntrinsics,
    extrinsics: CameraExtrinsics,
) -> npt.NDArray[np.float64]:
    """Project `(N, 3)` world points to `(N, 2)` pixels through the
    pinhole + Brown-Conrady model. Points with non-positive Z (behind
    the camera) are projected anyway; the caller is expected to filter
    them out via the visibility check it has from detection."""
    if points_world.ndim != 2 or points_world.shape[1] != 3:
        raise ValueError(f"points_world must be (N, 3); got {points_world.shape}")
    # World → camera frame.
    points_cam = (extrinsics.R @ points_world.T).T + extrinsics.t
    z = points_cam[:, 2]
    # Avoid divide-by-zero on Z=0 points — clamp to a tiny floor; such
    # points are unmeasurable anyway (singular projection) and the
    # optimizer will see a large residual.
    z_safe = np.where(np.abs(z) < 1e-12, 1e-12, z)
    xn = points_cam[:, 0] / z_safe
    yn = points_cam[:, 1] / z_safe
    x_dist, y_dist = _apply_distortion(xn, yn, intrinsics.distortion)
    u = intrinsics.fx * x_dist + intrinsics.cx
    v = intrinsics.fy * y_dist + intrinsics.cy
    return np.stack([u, v], axis=1)


def reprojection_errors(
    points_world: npt.NDArray[np.float64],
    points_observed_px: npt.NDArray[np.float64],
    intrinsics: CameraIntrinsics,
    extrinsics: CameraExtrinsics,
) -> npt.NDArray[np.float64]:
    """Per-point Euclidean reprojection error in pixels. Returns
    `(N,)` array of nonnegative magnitudes."""
    projected = project_points(points_world, intrinsics, extrinsics)
    diff = projected - points_observed_px
    out: npt.NDArray[np.float64] = np.sqrt(np.sum(diff * diff, axis=1))
    return out


def _pack_parameters(
    intrinsics: CameraIntrinsics, extrinsics_list: list[CameraExtrinsics]
) -> npt.NDArray[np.float64]:
    """Flatten the optimization variables into a 1-D vector.

    Layout: [fx, fy, cx, cy, k1, k2, p1, p2, k3,
             rvec_view_0 (3), tvec_view_0 (3),
             rvec_view_1 (3), tvec_view_1 (3),
             ...]

    Rotations are parameterized as Rodrigues 3-vectors (the rotation
    axis scaled by the angle in radians) — this is the standard
    smooth parameterization for SO(3) in nonlinear least squares.
    """
    intrinsic_params = np.array(
        [
            intrinsics.fx,
            intrinsics.fy,
            intrinsics.cx,
            intrinsics.cy,
            *intrinsics.distortion,
        ]
    )
    extrinsic_params: list[npt.NDArray[np.float64]] = []
    for ext in extrinsics_list:
        rvec = Rotation.from_matrix(ext.R).as_rotvec()
        extrinsic_params.append(np.concatenate([rvec, ext.t]))
    return np.concatenate([intrinsic_params, *extrinsic_params])


def _unpack_parameters(
    params: npt.NDArray[np.float64], n_views: int
) -> tuple[CameraIntrinsics, list[CameraExtrinsics]]:
    """Inverse of `_pack_parameters`."""
    fx, fy, cx, cy = params[:4]
    distortion = np.array(params[4:9], dtype=np.float64)
    K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)
    intrinsics = CameraIntrinsics(K=K, distortion=distortion)
    extrinsics_list: list[CameraExtrinsics] = []
    cursor = 9
    for _ in range(n_views):
        rvec = params[cursor : cursor + 3]
        tvec = params[cursor + 3 : cursor + 6]
        R = Rotation.from_rotvec(rvec).as_matrix()
        extrinsics_list.append(CameraExtrinsics(R=R, t=np.array(tvec, dtype=np.float64)))
        cursor += 6
    return intrinsics, extrinsics_list


def _residuals(
    params: npt.NDArray[np.float64],
    points_world: npt.NDArray[np.float64],
    observations: list[npt.NDArray[np.float64]],
) -> npt.NDArray[np.float64]:
    """Concatenated `(view × point × {u,v})` reprojection residuals.

    `least_squares` minimizes 0.5 * sum(residuals**2), so we hand it
    the raw signed differences (not magnitudes) — that way the
    Jacobian is well-defined at the optimum.
    """
    intrinsics, extrinsics_list = _unpack_parameters(params, len(observations))
    residuals: list[npt.NDArray[np.float64]] = []
    for ext, obs in zip(extrinsics_list, observations, strict=True):
        projected = project_points(points_world, intrinsics, ext)
        residuals.append((projected - obs).ravel())
    return np.concatenate(residuals)


def refine_calibration(
    points_world: npt.NDArray[np.float64],
    observations_per_view: list[npt.NDArray[np.float64]],
    initial_intrinsics: CameraIntrinsics,
    initial_extrinsics_per_view: list[CameraExtrinsics],
    max_iterations: int = 200,
) -> CalibrationResult:
    """Bundle-adjustment-style refinement of intrinsics + extrinsics.

    `observations_per_view[i]` is `(N, 2)` matching the same point
    indexing as `points_world` (the same N internal-corner labels
    across all views — caller is responsible for that matching, via
    the ChArUco marker IDs in the production path).

    The objective is the sum of squared per-point reprojection errors
    across all views. The optimizer uses `scipy.optimize.least_squares`
    with the Trust Region Reflective algorithm, which copes well with
    the rotation-vector / focal-length scale disparity in the
    parameter vector.

    Returns a `CalibrationResult` carrying the refined parameters and
    the p95 + mean reprojection error needed for the spec §4.3 "≤ 3 mm
    @ 5 m baseline" gate (translated to its pixel equivalent in the
    caller — we don't bake the conversion in here because it depends
    on the camera FOV).
    """
    if len(observations_per_view) != len(initial_extrinsics_per_view):
        raise ValueError(
            f"observations and initial extrinsics must have the same length; "
            f"got {len(observations_per_view)} vs {len(initial_extrinsics_per_view)}"
        )
    if not observations_per_view:
        raise ValueError("need at least one view to refine")
    n_corners = points_world.shape[0]
    for i, obs in enumerate(observations_per_view):
        if obs.shape != (n_corners, 2):
            raise ValueError(f"observation {i} must be ({n_corners}, 2); got {obs.shape}")

    initial_params = _pack_parameters(initial_intrinsics, initial_extrinsics_per_view)
    n_views = len(observations_per_view)

    result = least_squares(
        _residuals,
        initial_params,
        args=(points_world, observations_per_view),
        method="trf",
        max_nfev=max_iterations * len(initial_params),
        xtol=1e-10,
        ftol=1e-10,
    )

    refined_intrinsics, refined_extrinsics_list = _unpack_parameters(result.x, n_views)

    # Compute per-point errors for diagnostics. These are the same
    # quantities that get persisted in `CameraCalibration` rows so the
    # session-recalibration trigger (spec §4.4) can compare against
    # baseline.
    all_errors: list[npt.NDArray[np.float64]] = []
    for ext, obs in zip(refined_extrinsics_list, observations_per_view, strict=True):
        all_errors.append(reprojection_errors(points_world, obs, refined_intrinsics, ext))
    errors_flat = np.concatenate(all_errors)
    return CalibrationResult(
        intrinsics=refined_intrinsics,
        extrinsics=tuple(refined_extrinsics_list),
        reprojection_error_px_p95=float(np.percentile(errors_flat, 95.0)),
        reprojection_error_px_mean=float(np.mean(errors_flat)),
        iterations=int(result.nfev),
        converged=bool(result.success),
    )


def _make_intrinsics_from_fov(
    image_width_px: int,
    image_height_px: int,
    horizontal_fov_deg: float,
) -> CameraIntrinsics:
    """Build a no-distortion intrinsic from image size + horizontal FOV.

    Convenience for tests + initial-guess construction. Production
    code seeds from `cv2.calibrateCameraCharucoExtended` output.
    """
    fx = image_width_px / (2.0 * np.tan(np.deg2rad(horizontal_fov_deg) / 2.0))
    fy = fx
    cx = image_width_px / 2.0
    cy = image_height_px / 2.0
    K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)
    return CameraIntrinsics(K=K, distortion=np.zeros(5))


__all__ = [
    "CalibrationResult",
    "CameraExtrinsics",
    "CameraIntrinsics",
    "ChArUcoBoard",
    "project_points",
    "refine_calibration",
    "reprojection_errors",
    "_make_intrinsics_from_fov",  # exported for tests + spec-doc example
    "replace",  # re-export for callers updating intrinsics atomically
]
