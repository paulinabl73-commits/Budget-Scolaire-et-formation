"""Schémas du Module 3 : constats et plans d'action."""

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.finding import Criticality, FindingStatus


class FindingIn(BaseModel):
    titre: str = Field(min_length=1, max_length=300)
    critere: str | None = Field(default=None, max_length=20000)
    constat: str | None = Field(default=None, max_length=20000)
    cause: str | None = Field(default=None, max_length=20000)
    consequence: str | None = Field(default=None, max_length=20000)
    recommandation: str | None = Field(default=None, max_length=20000)
    criticite: Criticality = Criticality.MOYENNE
    risk_id: uuid.UUID | None = None
    control_id: uuid.UUID | None = None
    workpaper_ids: list[uuid.UUID] = Field(default=[], max_length=50)


class FindingUpdate(BaseModel):
    titre: str | None = Field(default=None, min_length=1, max_length=300)
    critere: str | None = Field(default=None, max_length=20000)
    constat: str | None = Field(default=None, max_length=20000)
    cause: str | None = Field(default=None, max_length=20000)
    consequence: str | None = Field(default=None, max_length=20000)
    recommandation: str | None = Field(default=None, max_length=20000)
    criticite: Criticality | None = None
    risk_id: uuid.UUID | None = None
    control_id: uuid.UUID | None = None
    workpaper_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    reference: str
    titre: str
    critere: str | None
    constat: str | None
    cause: str | None
    consequence: str | None
    recommandation: str | None
    criticite: Criticality
    risk_id: uuid.UUID | None
    control_id: uuid.UUID | None
    workpaper_ids: list[str]
    statut: FindingStatus
    audite_id: uuid.UUID | None
    envoye_le: dt.datetime | None
    date_limite_reponse: dt.date | None
    reponse_position: str | None
    reponse_commentaire: str | None
    repondu_le: dt.datetime | None
    valide_le: dt.datetime | None
    commentaire_validation: str | None
    created_at: dt.datetime | None = None
    # Calculés
    risque: str | None = None
    controle: str | None = None
    papiers: list[dict[str, Any]] = []
    audite_nom: str | None = None
    peut_modifier: bool = False


class EvidenceIn(BaseModel):
    type: str = Field(pattern="^(papier|piece_jointe|table)$")
    workpaper_id: uuid.UUID | None = None
    attachment_id: uuid.UUID | None = None
    dataset_id: uuid.UUID | None = None
    commentaire: str | None = Field(default=None, max_length=4000)


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    type: str
    workpaper_id: uuid.UUID | None
    attachment_id: uuid.UUID | None
    dataset_id: uuid.UUID | None
    empreinte: str | None
    extrait: dict[str, Any]
    commentaire: str | None
    created_at: dt.datetime | None = None
    libelle: str | None = None
    empreinte_actuelle: str | None = None


class PlanIn(BaseModel):
    description: str = Field(min_length=1, max_length=10000)
    responsable_id: uuid.UUID | None = None
    responsable_nom: str | None = Field(default=None, max_length=200)
    echeance: dt.date


class PlanUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    responsable_id: uuid.UUID | None = None
    responsable_nom: str | None = Field(default=None, max_length=200)
    echeance: dt.date | None = None


class PlanStatusIn(BaseModel):
    statut: str = Field(pattern="^(a_lancer|en_cours|realise|verifie|risque_accepte)$")
    commentaire: str | None = Field(default=None, max_length=4000)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    description: str
    responsable_id: uuid.UUID | None
    responsable_nom: str | None
    echeance: dt.date
    statut: str
    propose_par_audite: bool
    commentaire: str | None
    verifie_le: dt.datetime | None
    relances: list[dict[str, Any]]
    created_at: dt.datetime | None = None
    # Calculés
    responsable: str | None = None
    en_retard: bool = False
    constat_reference: str | None = None
    constat_titre: str | None = None
    mission_id: uuid.UUID | None = None
    transitions: list[str] = []
