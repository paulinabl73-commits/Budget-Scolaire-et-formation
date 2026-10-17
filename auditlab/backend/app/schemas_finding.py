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
