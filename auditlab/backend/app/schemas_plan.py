"""Schémas du lot 2 : univers d'audit, évaluation des risques, plan annuel."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

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
    created_at: datetime | None = None
