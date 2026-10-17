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
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
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


class AuditFile(TrackedMixin, Base):
    """Dossier de révision d'une entité pour un exercice (REV-02, REV-03, REV-04)."""

    __tablename__ = "audit_files"
    # Un seul dossier actif par entité et par exercice.
    __table_args__ = (
        Index("uq_audit_files_entite_exercice", "entity_id", "exercice", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("auditable_entities.id"), index=True)
    exercice: Mapped[int] = mapped_column(Integer)
    date_debut: Mapped[dt.date] = mapped_column(Date)
    date_fin: Mapped[dt.date] = mapped_column(Date)
    # REV-02 : référentiel principal (SYSCOHADA ou CIPRES) et, en option, restitution IFRS.
    framework_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounting_frameworks.id"))
    ifrs_framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounting_frameworks.id"), nullable=True
    )
    # REV-03 : cadre normatif de la mission.
    normative_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("normative_frameworks.id"), nullable=True
    )
    devise: Mapped[str] = mapped_column(String(3), default="XOF")
    # REV-04 : dossier de l'exercice précédent, d'où l'exercice N-1 est reporté.
    precedent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audit_files.id"), nullable=True
    )
    statut: Mapped[str] = mapped_column(String(20), default="ouvert")
    # REV-11 : seuils de signification.
    base_seuil: Mapped[str | None] = mapped_column(String(40), nullable=True)
    montant_base: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    pct_seuil: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    seuil_signification: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    pct_planification: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    seuil_planification: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    pct_insignifiant: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    seuil_insignifiant: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    justification_seuil: Mapped[str | None] = mapped_column(Text, nullable=True)
    # REV-12 : variation relative au-delà de laquelle une justification est demandée.
    seuil_variation_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("10"))


class TrialBalance(TrackedMixin, Base):
    """Balance générale, balance auxiliaire ou grand livre importé (REV-05).

    Statut « accepte » seulement si tous les contrôles bloquants passent (REV-06) ; le fichier
    source est conservé avec son empreinte. Un nouvel import remplace le précédent (suppression
    logique), l'historique reste consultable.
    """

    __tablename__ = "trial_balances"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    periode: Mapped[str] = mapped_column(String(5))  # N ou N-1
    type: Mapped[str] = mapped_column(String(30))  # balance, grand_livre, aux_clients…
    logiciel: Mapped[str] = mapped_column(String(20), default="generique")
    nom_fichier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    statut: Mapped[str] = mapped_column(String(20))  # accepte, rejete
    anomalies: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    avertissements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    totaux: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    nb_lignes: Mapped[int] = mapped_column(Integer, default=0)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    devise_source: Mapped[str | None] = mapped_column(String(3), nullable=True)
    cours: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    compte_collectif: Mapped[str | None] = mapped_column(String(20), nullable=True)


class TrialBalanceLine(Base):
    """Ligne de balance : non modifiable une fois importée (pas d'audit ligne à ligne)."""

    __tablename__ = "trial_balance_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trial_balance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trial_balances.id"), index=True)
    compte: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ouverture_debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    ouverture_credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    mouvement_debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    mouvement_credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    solde_debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    solde_credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))


class Currency(TrackedMixin, Base):
    """Devise et nombre de décimales (REV-07) : 0 pour le franc CFA."""

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), unique=True)
    libelle: Mapped[str] = mapped_column(String(100))
    decimales: Mapped[int] = mapped_column(Integer, default=2)


class ExchangeRate(TrackedMixin, Base):
    """Cours de conversion à une date : 1 unité de devise_source = taux unités de devise_cible."""

    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("devise_source", "devise_cible", "date"),)

    devise_source: Mapped[str] = mapped_column(String(3))
    devise_cible: Mapped[str] = mapped_column(String(3))
    date: Mapped[dt.date] = mapped_column(Date)
    taux: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AccountMapping(TrackedMixin, Base):
    """Affectation manuelle d'un compte à un poste (REV-08), qui prime sur l'affectation
    automatique par racine. Un compte à double sens peut recevoir un poste distinct pour un
    solde créditeur (REV-09). Reprise du dossier N-1 à la création du dossier (REV-04)."""

    __tablename__ = "account_mappings"
    __table_args__ = (
        Index("uq_account_mappings_dossier_compte", "audit_file_id", "compte", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    compte: Mapped[str] = mapped_column(String(30))
    poste: Mapped[str] = mapped_column(String(20))
    poste_crediteur: Mapped[str | None] = mapped_column(String(20), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnalyticalJustification(TrackedMixin, Base):
    """Justification d'une variation N/N-1 signalée par la revue analytique (REV-12)."""

    __tablename__ = "analytical_justifications"
    __table_args__ = (
        Index("uq_analytical_justifications_ligne", "audit_file_id", "niveau", "code",
              unique=True, postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    niveau: Mapped[str] = mapped_column(String(10))  # poste ou compte
    code: Mapped[str] = mapped_column(String(30))
    texte: Mapped[str] = mapped_column(Text)


class AssertionRisk(TrackedMixin, Base):
    """Évaluation d'un risque par cycle et par assertion (REV-14) ; le risque créé dans le
    programme de travail de la mission (Module 1) y est rattaché."""

    __tablename__ = "assertion_risks"
    __table_args__ = (
        Index("uq_assertion_risks_cellule", "audit_file_id", "cycle", "assertion", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    cycle: Mapped[str] = mapped_column(String(40))
    assertion: Mapped[str] = mapped_column(String(40))
    risque_inherent: Mapped[str | None] = mapped_column(String(10), nullable=True)
    risque_controle: Mapped[str | None] = mapped_column(String(10), nullable=True)
    risque_important: Mapped[bool] = mapped_column(Boolean, default=False)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risks.id"), nullable=True)


class Adjustment(TrackedMixin, Base):
    """Proposition d'écriture d'ajustement (REV-21) : correction ou reclassement, justifiée et
    liée à un papier de travail ; Proposée, puis Acceptée ou Refusée par l'entité. Seules les
    écritures acceptées modifient les soldes révisés ; les autres alimentent le tableau des
    anomalies non corrigées (REV-22)."""

    __tablename__ = "adjustments"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))  # correction, reclassement
    libelle: Mapped[str] = mapped_column(String(300))
    justification: Mapped[str] = mapped_column(Text)
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workpapers.id"), nullable=True
    )
    statut: Mapped[str] = mapped_column(String(20), default="proposee")
    decision_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    motif_decision: Mapped[str | None] = mapped_column(Text, nullable=True)


class AdjustmentLine(Base):
    """Ligne d'une écriture d'ajustement ; débit ou crédit."""

    __tablename__ = "adjustment_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    adjustment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("adjustments.id"), index=True)
    compte: Mapped[str] = mapped_column(String(30))
    libelle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))


class LeadScheduleReference(TrackedMixin, Base):
    """Renvoi d'une feuille maîtresse de cycle à un papier de travail (REV-15)."""

    __tablename__ = "lead_schedule_references"
    __table_args__ = (
        Index("uq_lead_schedule_references", "audit_file_id", "cycle", "workpaper_id",
              unique=True, postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    cycle: Mapped[str] = mapped_column(String(40))
    workpaper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workpapers.id"))
