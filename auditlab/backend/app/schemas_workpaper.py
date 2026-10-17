"""Schémas du lot 4 : papiers de travail, pièces jointes, signatures, notes de revue."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.workpaper import ControlAssessment, ReviewNoteStatus, SignoffType

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


class SignoffOut(BaseModel):
    id: uuid.UUID
    type: SignoffType
    user_id: uuid.UUID
    user_nom: str
    signed_at: datetime
    version: int
    hash_contenu: str
    annule_le: datetime | None = None
    motif_annulation: str | None = None


class SignoffIn(BaseModel):
    type: SignoffType


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
    # Dernière étape signée et valide : brouillon, prepare, revu ou approuve (AUD-18).
    statut_signature: str = "brouillon"
    signatures: list[SignoffOut] = []


class WorkpaperOut(WorkpaperSummary):
    objectif: str | None
    travaux: dict[str, Any]
    conclusion: str | None
    peut_modifier: bool = False
    signatures_possibles: list[SignoffType] = []
    motifs_refus: dict[str, str] = {}


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


ANCHOR_FIELDS = ("titre", "objectif", "travaux", "conclusion", "evaluation", "general")


class Anchor(BaseModel):
    champ: str = Field(default="travaux", pattern="^(" + "|".join(ANCHOR_FIELDS) + ")$")
    citation: str | None = Field(default=None, max_length=2000)


class ReviewNoteIn(BaseModel):
    texte: str = Field(min_length=1, max_length=5000)
    ancre: Anchor = Anchor()


class ReplyIn(BaseModel):
    texte: str = Field(min_length=1, max_length=5000)


class ReplyOut(BaseModel):
    id: uuid.UUID
    texte: str
    auteur: str | None
    created_at: datetime | None


class ReviewNoteOut(BaseModel):
    id: uuid.UUID
    workpaper_id: uuid.UUID
    workpaper_reference: str | None = None
    texte: str
    ancre: dict[str, Any]
    statut: ReviewNoteStatus
    auteur: str | None
    created_by: uuid.UUID | None
    created_at: datetime | None
    cloturee_le: datetime | None
    reponses: list[ReplyOut] = []
