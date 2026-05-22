"""Pydantic v2 DTOs for the AIMVISION API surface."""

from .athletes import AthleteOut
from .audit import AuditEventOut
from .camera_calibration import CalibrationHealthOut, CameraCalibrationIn, CameraCalibrationOut
from .coaching_note import CoachingNoteIn, CoachingNoteOut
from .cohorts import CohortOut
from .consent import ConsentGrantIn, ConsentOut, ConsentRevokeIn
from .drills import DrillOut
from .erasure import ErasureRequestIn, ErasureTicketOut
from .federation import (
    ClubMembershipOut,
    ClubStatus,
    FederationOverviewOut,
    TalentCohortOut,
)
from .orgs import OrgOut
from .progress import AthleteProgressOut, AtomDelta, SessionProgressOut
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
    "AthleteProgressOut",
    "AtomDelta",
    "AuditEventOut",
    "CalibrationHealthOut",
    "CameraCalibrationIn",
    "CameraCalibrationOut",
    "ClubMembershipOut",
    "ClubStatus",
    "CoachingNoteIn",
    "CoachingNoteOut",
    "CohortOut",
    "ConsentGrantIn",
    "ConsentOut",
    "ConsentRevokeIn",
    "DrillOut",
    "ErasureRequestIn",
    "ErasureTicketOut",
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
    "SessionProgressOut",
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
