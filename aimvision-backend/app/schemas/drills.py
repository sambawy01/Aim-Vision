"""Drill catalog DTO."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DrillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    discipline: str
    target_categories: list[str]
