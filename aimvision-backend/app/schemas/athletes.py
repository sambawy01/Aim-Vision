"""Athlete view DTOs.

An "athlete" is a User that holds at least one active Membership
with `role=athlete` in the principal's tenant. The web dashboard
+ mobile coach app consume these endpoints to pick the athlete
for a new session.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AthleteOut(BaseModel):
    """A user surfaced as an athlete in the caller's tenant. The
    `joined_at` is the User's `created_at` — we don't have a
    dedicated "joined the federation" timestamp yet, but the row
    creation is a reasonable proxy."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    email: str | None
    joined_at: datetime
