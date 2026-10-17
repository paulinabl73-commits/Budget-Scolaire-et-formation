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


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workpaper_id: uuid.UUID
    nom_fichier: str
    content_type: str
    taille: int
    sha256: str
    version: int
    created_at: datetime | None = None
    url: str = ""


class TickmarkIn(BaseModel):
    symbole: str = Field(min_length=1, max_length=4)
    libelle: str = Field(min_length=1, max_length=200)
    couleur: str = Field(default="#1f5fa8", pattern=r"^#[0-9a-fA-F]{6}$")
    ordre: int = 0


class TickmarkUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=200)
    couleur: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    ordre: int | None = None
    actif: bool | None = None


class TickmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbole: str
    libelle: str
    couleur: str
    ordre: int
    actif: bool


class VersionSummary(BaseModel):
    version: int
    created_at: datetime | None
    auteur: str | None
    hash_contenu: str


class VersionOut(VersionSummary):
    contenu: dict[str, Any]


class DiffSegment(BaseModel):
    type: str  # egal, ajoute, supprime
    texte: str


class FieldDiff(BaseModel):
    champ: str
    libelle: str
    modifie: bool
    segments: list[DiffSegment]


class CompareOut(BaseModel):
    de: int
    a: int
    champs: list[FieldDiff]
