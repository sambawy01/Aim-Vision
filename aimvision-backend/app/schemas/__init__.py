"""Pydantic v2 DTOs for the AIMVISION API surface."""

from .athletes import AthleteOut
from .audit import AuditEventOut
from .camera_calibration import CalibrationHealthOut, CameraCalibrationIn, CameraCalibrationOut
from .cohorts import CohortOut
from .consent import ConsentGrantIn, ConsentOut, ConsentRevokeIn
from .federation import (
    ClubMembershipOut,
    ClubStatus,
    FederationOverviewOut,
    TalentCohortOut,
)
from .orgs import OrgOut
from .session import (
    AlignmentIn,
    ProcessSessionIn,
    ProcessSessionOut,
    RecordingOut,
    SessionCreateIn,
    SessionEndIn,
    SessionOut,
    SessionSummaryOut,
    ShotEventIn,
    ShotEventOut,
    ShotIn,
    ShotOut,
)
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
    "AthleteOut",
    "AuditEventOut",
    "CalibrationHealthOut",
    "CameraCalibrationIn",
    "CameraCalibrationOut",
    "ClubMembershipOut",
    "ClubStatus",
    "CohortOut",
    "ConsentGrantIn",
    "ConsentOut",
    "ConsentRevokeIn",
    "FederationOverviewOut",
    "HealthOut",
    "LoginIn",
    "LoginOut",
    "OrgOut",
    "PrincipalOut",
    "ProcessSessionIn",
    "ProcessSessionOut",
    "RecordingOut",
    "SessionCreateIn",
    "SessionEndIn",
    "SessionOut",
    "SessionSummaryOut",
    "ShotEventIn",
    "ShotEventOut",
    "ShotIn",
    "ShotOut",
    "SignupIn",
    "TalentCohortOut",
    "UserOut",
    "VersionOut",
]
