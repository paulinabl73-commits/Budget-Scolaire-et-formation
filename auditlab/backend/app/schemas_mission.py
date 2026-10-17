"""Schémas du lot 3 : missions, temps, bibliothèque, matrice, procédures, modèles."""

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.engagement import EngagementStatus, MissionRole


class MemberIn(BaseModel):
    user_id: uuid.UUID
    role_mission: MissionRole


class MemberOut(BaseModel):
    user_id: uuid.UUID
    nom: str
    email: str
    role_mission: MissionRole


class _Dates(BaseModel):
    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        debut = getattr(self, "date_debut", None)
        fin = getattr(self, "date_fin", None)
        if debut and fin and fin < debut:
            raise ValueError("La date de fin précède la date de début")
        return self


class EngagementIn(_Dates):
    plan_item_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    titre: str | None = Field(default=None, max_length=300)
    perimetre: str | None = None
    objectifs: str | None = None
    date_debut: date | None = None
    date_fin: date | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=10000)
    membres: list[MemberIn] = []


class EngagementUpdate(_Dates):
    titre: str | None = Field(default=None, min_length=1, max_length=300)
    perimetre: str | None = None
    objectifs: str | None = None
    date_debut: date | None = None
    date_fin: date | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=10000)


class StatusIn(BaseModel):
    statut: EngagementStatus


class EngagementSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    titre: str
    statut: EngagementStatus
    date_debut: date
    date_fin: date
    budget_jours: float
    jours_consommes: float = 0
    entity_id: uuid.UUID | None
    entity_nom: str | None = None
    plan_id: uuid.UUID | None
    plan_item_id: uuid.UUID | None
    chef_nom: str | None = None
    mon_role: MissionRole | None = None


class EngagementOut(EngagementSummary):
    perimetre: str | None
    objectifs: str | None
    membres: list[MemberOut]
    transitions: list[EngagementStatus] = []
    peut_gerer: bool = False
    created_at: datetime | None = None
