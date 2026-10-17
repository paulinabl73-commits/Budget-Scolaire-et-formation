"""Schémas du lot 2 : univers d'audit, évaluation des risques, plan annuel."""

import uuid
from datetime import date, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.plan import PlanStatus
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


class MapEntity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    type: EntityType
    score_risque: float | None
    impact: float | None
    probabilite: float | None


class MapCell(BaseModel):
    impact: int
    probabilite: int
    entites: list[MapEntity]


class RiskMapOut(BaseModel):
    echelle: int
    cellules: list[MapCell]
    non_evaluees: list[MapEntity]


class PlanIn(BaseModel):
    annee: int = Field(ge=2000, le=2100)
    capacite_jours: float | None = Field(default=None, gt=0)
    commentaire: str | None = None


class PlanUpdate(BaseModel):
    capacite_jours: float | None = Field(default=None, gt=0)
    commentaire: str | None = None


class _Period(BaseModel):
    @model_validator(mode="after")
    def _check_period(self) -> Self:
        debut = getattr(self, "periode_debut", None)
        fin = getattr(self, "periode_fin", None)
        if debut and fin and fin < debut:
            raise ValueError("La fin de la période précède son début")
        return self


class PlanItemIn(_Period):
    entity_id: uuid.UUID
    titre: str | None = Field(default=None, max_length=300)
    budget_jours: float = Field(gt=0, le=10000)
    periode_debut: date
    periode_fin: date
    justification: str | None = None


class PlanItemUpdate(_Period):
    titre: str | None = Field(default=None, min_length=1, max_length=300)
    budget_jours: float | None = Field(default=None, gt=0, le=10000)
    periode_debut: date | None = None
    periode_fin: date | None = None
    justification: str | None = None


class PlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_id: uuid.UUID
    entity_nom: str
    score_risque: float | None
    titre: str
    budget_jours: float
    periode_debut: date
    periode_fin: date
    justification: str | None


class PlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    annee: int
    version: int
    statut: PlanStatus
    capacite_jours: float | None
    commentaire: str | None
    nb_missions: int
    total_jours: float
    valide_par: uuid.UUID | None = None
    valide_par_nom: str | None = None
    valide_le: datetime | None = None
    version_precedente_id: uuid.UUID | None = None
    created_at: datetime | None = None


class PlanOut(PlanSummary):
    items: list[PlanItemOut]
