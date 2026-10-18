"""Schémas du lot 3 : missions, temps, bibliothèque, matrice, procédures, modèles."""

import datetime as dt
import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.engagement import EngagementStatus, MissionRole, TimeActivity
from app.models.program import (
    ControlNature,
    ControlType,
    Cycle,
    Frequency,
    ProcedureStatus,
    RiskCategory,
    TestType,
)


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
    template_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    titre: str | None = Field(default=None, max_length=300)
    perimetre: str | None = None
    objectifs: str | None = None
    date_debut: date | None = None
    date_fin: date | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=10000)
    membres: list[MemberIn] = []
    mode: Literal["audit", "inspection_cipres"] = "audit"


class EngagementUpdate(_Dates):
    titre: str | None = Field(default=None, min_length=1, max_length=300)
    perimetre: str | None = None
    objectifs: str | None = None
    date_debut: date | None = None
    date_fin: date | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=10000)


class StatusIn(BaseModel):
    statut: EngagementStatus


class TransitionOut(BaseModel):
    statut: EngagementStatus
    sens: str  # "suivant" ou "precedent"
    motif_blocage: str | None = None


class StatusChangeOut(BaseModel):
    horodatage: datetime
    utilisateur: str | None
    avant: EngagementStatus
    apres: EngagementStatus


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
    mode: str = "audit"


class EngagementOut(EngagementSummary):
    perimetre: str | None
    objectifs: str | None
    membres: list[MemberOut]
    transitions: list[TransitionOut] = []
    peut_gerer: bool = False
    cloturee_le: datetime | None = None
    created_at: datetime | None = None


class TimeEntryIn(BaseModel):
    date: dt.date
    heures: float = Field(gt=0, le=24, multiple_of=0.25)
    activite: TimeActivity
    commentaire: str | None = Field(default=None, max_length=500)


class TimeEntryUpdate(BaseModel):
    date: dt.date | None = None
    heures: float | None = Field(default=None, gt=0, le=24, multiple_of=0.25)
    activite: TimeActivity | None = None
    commentaire: str | None = Field(default=None, max_length=500)


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_nom: str
    date: dt.date
    heures: float
    activite: TimeActivity
    commentaire: str | None


class TimeLine(BaseModel):
    cle: str
    libelle: str
    jours: float


class TimeSummary(BaseModel):
    budget_jours: float
    jours_consommes: float
    ecart_jours: float
    taux_consommation: float
    heures_par_jour: float
    par_personne: list[TimeLine]
    par_activite: list[TimeLine]


class RiskIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=300)
    description: str | None = None
    cycle: Cycle
    categorie: RiskCategory


class RiskUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    cycle: Cycle | None = None
    categorie: RiskCategory | None = None


class ControlIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=300)
    description: str | None = None
    cycle: Cycle
    type_controle: ControlType
    nature: ControlNature
    frequence: Frequency


class ControlUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    cycle: Cycle | None = None
    type_controle: ControlType | None = None
    nature: ControlNature | None = None
    frequence: Frequency | None = None


class ProcedureIn(BaseModel):
    control_id: uuid.UUID
    description: str = Field(min_length=1)
    type_test: TestType


class ProcedureUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    type_test: TestType | None = None


class ProcedureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    control_id: uuid.UUID
    reference: str | None
    description: str
    type_test: TestType
    assigne_a: uuid.UUID | None = None
    assigne_nom: str | None = None
    echeance: date | None = None
    statut: ProcedureStatus = ProcedureStatus.A_FAIRE
    en_retard: bool = False


class AssignmentIn(BaseModel):
    assigne_a: uuid.UUID | None
    echeance: date | None


class ProcedureStatusIn(BaseModel):
    statut: ProcedureStatus


class MyProcedureOut(ProcedureOut):
    engagement_id: uuid.UUID
    engagement_reference: str
    engagement_titre: str
    controle: str


class ControlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    libelle: str
    description: str | None
    cycle: Cycle
    type_controle: ControlType
    nature: ControlNature
    frequence: Frequency
    source_id: uuid.UUID | None = None
    procedures: list[ProcedureOut] = []


class RiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    libelle: str
    description: str | None
    cycle: Cycle
    categorie: RiskCategory
    source_id: uuid.UUID | None = None
    controles: list[ControlOut] = []


class LinkIn(BaseModel):
    control_ids: list[uuid.UUID]


class MissionRiskIn(BaseModel):
    """Copie d'un risque de la bibliothèque, ou risque propre à la mission."""

    library_risk_id: uuid.UUID | None = None
    libelle: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    cycle: Cycle | None = None
    categorie: RiskCategory | None = None


class MissionControlIn(BaseModel):
    library_control_id: uuid.UUID | None = None
    libelle: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    cycle: Cycle | None = None
    type_controle: ControlType | None = None
    nature: ControlNature | None = None
    frequence: Frequency | None = None
    risk_ids: list[uuid.UUID] = []


class MatrixOut(BaseModel):
    risques: list[RiskOut]
    controles: list[ControlOut]


class TemplateIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    description: str | None = None
    perimetre: str | None = None
    objectifs: str | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=10000)
    from_engagement_id: uuid.UUID | None = None
    library_risk_ids: list[uuid.UUID] = []


class TemplateUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    perimetre: str | None = None
    objectifs: str | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=10000)


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    description: str | None
    perimetre: str | None
    objectifs: str | None
    budget_jours: float | None
    nb_risques: int
    nb_controles: int
    nb_procedures: int
    contenu: dict
