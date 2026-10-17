"""Données analysées (Module 2) : seules les métadonnées sont en base, les lignes en Parquet."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


class DatasetKind(StrEnum):
    IMPORT = "import"  # table importée, jamais modifiée (DAT-05)
    VUE = "vue"  # champs calculés sur une table, sans copie (DAT-06)
    ANALYSE = "analyse"  # table produite par une analyse (lot 6)


class DatasetStatus(StrEnum):
    EN_COURS = "en_cours"
    PRET = "pret"
    ERREUR = "erreur"


class Dataset(TrackedMixin, Base):
    __tablename__ = "datasets"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    nom: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    statut: Mapped[str] = mapped_column(String(20), default=DatasetStatus.EN_COURS.value)
    erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True, index=True
    )
    # Source (import) : nom, format, empreinte et copie conservée du fichier d'origine.
    source_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_taille: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Résultat : fichier Parquet (lecture seule), volumétrie, schéma et totaux de contrôle.
    chemin_parquet: Mapped[str | None] = mapped_column(String(300), nullable=True)
    nb_lignes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nb_colonnes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    totaux_controle: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Vue : définition des champs calculés (DAT-06).
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    duree_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
