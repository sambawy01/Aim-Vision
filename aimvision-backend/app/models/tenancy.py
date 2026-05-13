"""Tenancy domain: Account, User, Org, Membership, Cohort, AthleteProfile."""

from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class OrgKind(enum.StrEnum):
    solo = "solo"
    club = "club"
    federation = "federation"


class Role(enum.StrEnum):
    coach = "coach"
    athlete = "athlete"
    admin = "admin"
    parent = "parent"
    # Federation-tier role: cross-club admin over a Federation Org and its
    # subordinate Clubs. Authorization layer treats this as a superset of
    # `admin` scoped to the federation hierarchy. Per V2 plan §EPIC 4.3.
    federation_admin = "federation_admin"


class Account(Base, TimestampMixin):
    """Billing/account boundary. One account may own multiple users (parent + minors)."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Org(Base, TimestampMixin, TenantScopedMixin):
    """An organization: solo (synthetic), club, or federation."""

    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    kind: Mapped[OrgKind] = mapped_column(SAEnum(OrgKind, name="org_kind"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    federation_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("orgs.id", ondelete="SET NULL"), nullable=True
    )


class Membership(Base, TimestampMixin, TenantScopedMixin):
    """User's role within an org."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id", "role", name="uq_membership"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="membership_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Cohort(Base, TimestampMixin, TenantScopedMixin):
    """A group of athletes within an org (federation talent group, club squad)."""

    __tablename__ = "cohorts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class AthleteProfile(Base, TimestampMixin, TenantScopedMixin):
    """Athlete-facing profile, scoped per tenancy (an athlete in two clubs has two profiles)."""

    __tablename__ = "athlete_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_athlete_profile_user_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cohort_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True
    )
    discipline: Mapped[str] = mapped_column(String(64), nullable=False, default="trap")
    handedness: Mapped[str] = mapped_column(String(8), nullable=False, default="right")


class CoachProfile(Base, TimestampMixin, TenantScopedMixin):
    """Coach-side profile. One row per (user, tenant) — a coach contracting with
    two federations carries two profiles, each scoped to its own tenant.

    Sprint 4 EPIC 4.3 deliverable per V2 plan; complements `AthleteProfile`.
    """

    __tablename__ = "coach_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_coach_profile_user_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of {issuer, level, issued_at, expires_at?}. Free-form because the
    # certification landscape is fragmented (ISSF, national federations, NRA,
    # private bodies); a strict enum would force premature normalization.
    certifications: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    # JSON list of discipline strings: "trap", "skeet", "sporting", "doubles", etc.
    specializations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    accepting_clients: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
