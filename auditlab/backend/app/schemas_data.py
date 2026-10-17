"""Schémas du Module 2 : jeux de données, imports, requêtes."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

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
    definition: dict[str, Any]
    options: dict[str, Any]
    duree_ms: int | None
    created_at: datetime | None = None
    lecture_seule: bool = True
