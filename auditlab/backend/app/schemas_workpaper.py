"""Schémas du lot 4 : papiers de travail, pièces jointes, signatures, notes de revue."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.workpaper import ControlAssessment

REFERENCE_PATTERN = r"^[A-Z0-9]{1,6}(-[A-Z0-9]+(\.[0-9]+)*)?$"


class WorkpaperIn(BaseModel):
    reference: str = Field(pattern=REFERENCE_PATTERN, max_length=30)
    titre: str = Field(min_length=1, max_length=300)
    procedure_id: uuid.UUID | None = None
    objectif: str | None = None
    travaux: dict[str, Any] | None = None
    conclusion: str | None = None
    evaluation: ControlAssessment | None = None


class WorkpaperUpdate(BaseModel):
    reference: str | None = Field(default=None, pattern=REFERENCE_PATTERN, max_length=30)
    titre: str | None = Field(default=None, min_length=1, max_length=300)
    procedure_id: uuid.UUID | None = None
    objectif: str | None = None
    travaux: dict[str, Any] | None = None
    conclusion: str | None = None
    evaluation: ControlAssessment | None = None


class WorkpaperSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    reference: str
    titre: str
    procedure_id: uuid.UUID | None
    procedure_reference: str | None = None
    evaluation: ControlAssessment | None
    version: int
    updated_at: datetime | None = None


class WorkpaperOut(WorkpaperSummary):
    objectif: str | None
    travaux: dict[str, Any]
    conclusion: str | None
    peut_modifier: bool = False
