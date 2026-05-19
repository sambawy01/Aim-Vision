"""Pydantic v2 DTOs for the AIMVISION API surface."""

from .audit import AuditEventOut
from .camera_calibration import CameraCalibrationIn, CameraCalibrationOut
from .consent import ConsentGrantIn, ConsentOut, ConsentRevokeIn
from .federation import (
    ClubMembershipOut,
    ClubStatus,
    FederationOverviewOut,
    TalentCohortOut,
)
from .session import AlignmentIn, RecordingOut, SessionOut, ShotOut
from .tenancy import (
    HealthOut,
    LoginIn,
    LoginOut,
    PrincipalOut,
    SignupIn,
    UserOut,
    VersionOut,
)

__all__ = [
    "AlignmentIn",
    "AuditEventOut",
    "CameraCalibrationIn",
    "CameraCalibrationOut",
    "ClubMembershipOut",
    "ClubStatus",
    "ConsentGrantIn",
    "ConsentOut",
    "ConsentRevokeIn",
    "FederationOverviewOut",
    "HealthOut",
    "LoginIn",
    "LoginOut",
    "PrincipalOut",
    "RecordingOut",
    "SessionOut",
    "ShotOut",
    "SignupIn",
    "TalentCohortOut",
    "UserOut",
    "VersionOut",
]
