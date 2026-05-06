"""Pydantic v2 DTOs for the AIMVISION API surface."""

from .audit import AuditEventOut
from .consent import ConsentGrantIn, ConsentOut, ConsentRevokeIn
from .session import RecordingOut, SessionOut, ShotOut
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
    "AuditEventOut",
    "ConsentGrantIn",
    "ConsentOut",
    "ConsentRevokeIn",
    "HealthOut",
    "LoginIn",
    "LoginOut",
    "PrincipalOut",
    "RecordingOut",
    "SessionOut",
    "ShotOut",
    "SignupIn",
    "UserOut",
    "VersionOut",
]
