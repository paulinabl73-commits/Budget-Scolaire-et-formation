"""Schémas du lot 2 : univers d'audit, évaluation des risques, plan annuel."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.risk import Axis, CriterionMode
from app.models.universe import EntityType


class EntityIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    type: EntityType
    parent_id: uuid.UUID | None = None
    description: str | None = None
    responsable: str | None = Field(default=None, max_length=200)
    date_dernier_audit: date | None = None


class EntityUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=200)
    type: EntityType | None = None
    parent_id: uuid.UUID | None = None
    description: str | None = None
    responsable: str | None = Field(default=None, max_length=200)
    date_dernier_audit: date | None = None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    type: EntityType
    parent_id: uuid.UUID | None
    description: str | None
    responsable: str | None
    date_dernier_audit: date | None
    score_risque: float | None
    impact: float | None
    probabilite: float | None
    date_evaluation: date | None
    created_at: datetime | None = None


class CriterionIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9_]+$")
    libelle: str = Field(min_length=1, max_length=200)
    description: str | None = None
    axe: Axis
    mode: CriterionMode = CriterionMode.NOTE
    poids: float = Field(default=1.0, gt=0, le=100)
    ordre: int = 0


class CriterionUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    axe: Axis | None = None
    mode: CriterionMode | None = None
    poids: float | None = Field(default=None, gt=0, le=100)
    ordre: int | None = None
    actif: bool | None = None


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    libelle: str
    description: str | None
    axe: Axis
    mode: CriterionMode
    poids: float
    ordre: int
    actif: bool


class AssessmentIn(BaseModel):
    notes: dict[str, int] = {}
    date_evaluation: date | None = None
    commentaire: str | None = None


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_id: uuid.UUID
    date_evaluation: date
    criteres: list[dict[str, Any]]
    score: float
    impact: float | None
    probabilite: float | None
    commentaire: str | None
    created_at: datetime | None = None
    created_by: uuid.UUID | None = None
