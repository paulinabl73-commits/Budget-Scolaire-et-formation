"""Module 5 : révision des comptes (SYSCOHADA, IFRS, CIPRES).

Les référentiels sont des données versionnées (REV-01) : plan de comptes, postes des états
avec leurs règles d'affectation, ratios, règles de contrôle et paramètres réglementaires.
Aucune valeur réglementaire n'est écrite dans le programme (CIP-09).
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin

MONEY = Numeric(20, 2)


class AccountingFramework(TrackedMixin, Base):
    """Référentiel comptable versionné (REV-01). Une mise à jour crée une nouvelle version ;
    un dossier garde la version avec laquelle il a été ouvert."""

    __tablename__ = "accounting_frameworks"
    __table_args__ = (UniqueConstraint("code", "version", "pays"),)

    code: Mapped[str] = mapped_column(String(20))  # SYSCOHADA, IFRS, CIPRES
    version: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(300))
    pays: Mapped[str] = mapped_column(String(40), default="OHADA")
    date_effet: Mapped[dt.date] = mapped_column(Date)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    fichier_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ratios: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    bases_seuil: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    regles: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    branches: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class FrameworkAccount(Base):
    """Compte du plan d'un référentiel (racine ou compte détaillé)."""

    __tablename__ = "framework_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounting_frameworks.id"), index=True
    )
    numero: Mapped[str] = mapped_column(String(20))
    libelle: Mapped[str] = mapped_column(String(300))
    classe: Mapped[int] = mapped_column(Integer)
    sens: Mapped[str | None] = mapped_column(String(10), nullable=True)
    branche: Mapped[str | None] = mapped_column(String(20), nullable=True)


class StatementLine(Base):
    """Poste d'un état financier : racines de comptes affectées (avec règle de sens pour les
    comptes à double sens, REV-09) et/ou formule sur d'autres postes (totaux)."""

    __tablename__ = "statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounting_frameworks.id"), index=True
    )
    etat: Mapped[str] = mapped_column(String(40))  # bilan_actif, bilan_passif, compte_resultat…
    code: Mapped[str] = mapped_column(String(20))
    libelle: Mapped[str] = mapped_column(String(300))
    nature: Mapped[str] = mapped_column(String(10))  # actif, passif, charge, produit
    racines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    formule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ordre: Mapped[int] = mapped_column(Integer)
    niveau: Mapped[int] = mapped_column(Integer, default=1)


class RegulatoryParameter(TrackedMixin, Base):
    """Taux, plafond ou limite réglementaire, par pays et par exercice (CIP-09)."""

    __tablename__ = "regulatory_parameters"

    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounting_frameworks.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    libelle: Mapped[str] = mapped_column(String(300))
    valeur: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unite: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pays: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exercice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branche: Mapped[str | None] = mapped_column(String(20), nullable=True)


class NormativeFramework(TrackedMixin, Base):
    """Cadre normatif d'une mission (REV-03) : ISA, normes nationales, règlement CIPRES…"""

    __tablename__ = "normative_frameworks"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    libelle: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
