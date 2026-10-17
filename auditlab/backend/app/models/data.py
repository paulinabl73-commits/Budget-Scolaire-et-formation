"""Données analysées (Module 2) : seules les métadonnées sont en base, les lignes en Parquet."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
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
    # Empreinte du fichier Parquet produit : preuve que la table n'a pas changé (DAT-04).
    parquet_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Vue : définition des champs calculés (DAT-06).
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    duree_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Analyse (lot 6) : opération appliquée et résultat de synthèse (tests, graphiques).
    operation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resultat: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Upload(TrackedMixin, Base):
    """Fichier source déposé pour un import, conservé tel quel comme preuve (DAT-04)."""

    __tablename__ = "uploads"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    nom_fichier: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(20))
    taille: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)


class DataSource(TrackedMixin, Base):
    """Base de données source (SQL ou ODBC), déclarée par l'administrateur (DAT-01).

    Les utilisateurs choisissent une source déclarée et saisissent une requête de lecture ;
    ils ne saisissent jamais d'adresse de connexion (pas de rebond vers le réseau interne).
    """

    __tablename__ = "data_sources"
    __audit_masked__ = ("url",)

    nom: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Adresse SQLAlchemy, ex. postgresql+psycopg://lecteur:…@hote/base, mssql+pyodbc://…
    url: Mapped[str] = mapped_column(Text)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class SampleEvaluation(TrackedMixin, Base):
    """Évaluation d'un échantillon MUS (DAT-23) : erreurs constatées et projection."""

    __tablename__ = "sample_evaluations"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), index=True)
    confiance: Mapped[str] = mapped_column(String(10))
    erreur_tolerable: Mapped[str | None] = mapped_column(String(40), nullable=True)
    erreurs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    resultat: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AnalysisOperation(TrackedMixin, Base):
    """Opération qui a produit une table (import, vue, analyse, script) : forme la lignée
    (DAT-24). Une ligne par exécution ; la plus récente d'une table fait foi."""

    __tablename__ = "analysis_operations"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))  # import, vue, ou code d'analyse
    parametres: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    entrees: Mapped[list[str]] = mapped_column(JSONB, default=list)  # ids des tables d'entrée
    sortie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), index=True)
    statut: Mapped[str] = mapped_column(String(20))
    duree_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    empreinte: Mapped[str | None] = mapped_column(String(64), nullable=True)
