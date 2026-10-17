"""Schémas du Module 2 : jeux de données, imports, requêtes."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.data import DatasetKind, DatasetStatus


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    nom: str
    description: str | None
    kind: DatasetKind
    statut: DatasetStatus
    erreur: str | None
    parent_dataset_id: uuid.UUID | None
    source_nom: str | None
    source_format: str | None
    source_sha256: str | None
    source_taille: int | None
    nb_lignes: int | None
    nb_colonnes: int | None
    schema: list[dict[str, Any]]
    totaux_controle: dict[str, Any]
    parquet_sha256: str | None = None
    definition: dict[str, Any]
    options: dict[str, Any]
    duree_ms: int | None
    operation: str | None = None
    resultat: dict[str, Any] = {}
    created_at: datetime | None = None
    lecture_seule: bool = True


class ColumnSpecIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    type: str | None = Field(default=None, pattern="^(texte|entier|decimal|date|booleen)$")
    debut: int | None = Field(default=None, ge=1)
    fin: int | None = Field(default=None, ge=1)


class ReadOptionsIn(BaseModel):
    format: str = Field(pattern="^(csv|txt|txt_fixe|xlsx|xls|json|parquet|pdf)$")
    encodage: str = Field(default="utf-8", pattern="^(utf-8|cp1252|latin-1|iso-8859-15)$")
    separateur: str = Field(default=";", min_length=1, max_length=1)
    guillemet: str | None = '"'
    entete: bool = True
    lignes_ignorees: int = Field(default=0, ge=0, le=1000)
    decimal: str = Field(default=",", pattern=r"^[,.]$")
    milliers: str = Field(default=" ", pattern=r"^[ .',]?$")
    format_date: str = Field(default="%d/%m/%Y", max_length=30)
    feuille: str | int | None = None
    colonnes: list[ColumnSpecIn] = []
    # PDF (DAT-03)
    pages: str | None = Field(default=None, pattern=r"^[0-9 ,\-]*$")
    mode_pdf: str = Field(default="tableaux", pattern="^(tableaux|colonnes)$")


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom_fichier: str
    format: str
    taille: int
    sha256: str
    created_at: datetime | None = None


class ImportIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    description: str | None = None
    upload_id: uuid.UUID | None = None
    options: ReadOptionsIn | None = None
    source_id: uuid.UUID | None = None
    requete: str | None = Field(default=None, max_length=20000)


class DataSourceIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    description: str | None = None
    url: str = Field(min_length=5)


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    description: str | None
    actif: bool
    dialecte: str = ""


class IntegrityOut(BaseModel):
    source_intacte: bool | None
    table_intacte: bool | None
    source_sha256: str | None
    parquet_sha256: str | None
