"""Module 6 : portefeuille de dossiers clients d'un cabinet d'expertise comptable."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


class Client(TrackedMixin, Base):
    """Dossier client permanent (RCO-01) ; l'entité de rattachement est de type « client »."""

    __tablename__ = "clients"

    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("auditable_entities.id"), index=True)
    raison_sociale: Mapped[str] = mapped_column(String(200))
    forme_juridique: Mapped[str] = mapped_column(String(30))
    regime_fiscal: Mapped[str] = mapped_column(String(40))
    framework_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounting_frameworks.id"))
    pays: Mapped[str] = mapped_column(String(40))
    devise: Mapped[str] = mapped_column(String(3), default="XOF")
    # Date de clôture de l'exercice (jour et mois), 31 décembre le plus souvent.
    jour_cloture: Mapped[int] = mapped_column(Integer, default=31)
    mois_cloture: Mapped[int] = mapped_column(Integer, default=12)
    taille: Mapped[str] = mapped_column(String(20), default="pme")  # tpe, pme, grande (RCO-07)
    identifiant_fiscal: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rccm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    collaborateur_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    superviseur_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    budget_jours: Mapped[float] = mapped_column(Float, default=5)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class Closing(TrackedMixin, Base):
    """Clôture d'un exercice d'un client : mission (mode « revision_comptable ») et dossier de
    révision du Module 5 qui en porte la balance, l'affectation et les états."""

    __tablename__ = "closings"
    __table_args__ = (
        Index("uq_closings_exercice", "client_id", "exercice", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    exercice: Mapped[int] = mapped_column(Integer)
    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    etape: Mapped[str] = mapped_column(String(20), default="pieces")
    # Date de franchissement de chaque étape (RCO-02).
    etapes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    date_depot: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class CalendarRule(TrackedMixin, Base):
    """Échéance fiscale, sociale ou juridique d'un pays (RCO-03), saisie par le cabinet.

    Périodicité : « mensuelle » et « trimestrielle » (jour J du mois qui suit la période),
    « annuelle » (jour et mois fixes), « cloture » (N mois après la clôture, au jour J ou au
    même quantième). `regimes` vide : tous les régimes fiscaux.
    """

    __tablename__ = "calendar_rules"

    pays: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(300))
    nature: Mapped[str] = mapped_column(String(20))  # fiscal, social, juridique
    periodicite: Mapped[str] = mapped_column(String(20))
    jour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mois: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decalage_mois: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regimes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class ClientDeadline(TrackedMixin, Base):
    """Suivi d'une échéance d'un client : faite, alertes envoyées (une par délai)."""

    __tablename__ = "client_deadlines"
    __table_args__ = (
        Index("uq_client_deadlines", "client_id", "rule_id", "echeance", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendar_rules.id"), index=True)
    echeance: Mapped[dt.date] = mapped_column(Date)
    fait_le: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    alertes: Mapped[list[int]] = mapped_column(JSONB, default=list)


class ClientFile(TrackedMixin, Base):
    """Fichier d'un dossier client (pièce déposée, document permanent, justificatif de
    compte), conservé avec son empreinte."""

    __tablename__ = "client_files"

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    objet: Mapped[str] = mapped_column(String(20))  # piece, permanent, justification
    objet_id: Mapped[uuid.UUID] = mapped_column(index=True)
    nom_fichier: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    taille: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)


class PieceRequest(TrackedMixin, Base):
    """Pièce demandée au client pour une clôture (RCO-04), envoyée par le portail."""

    __tablename__ = "piece_requests"

    closing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("closings.id"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    libelle: Mapped[str] = mapped_column(String(300))
    categorie: Mapped[str] = mapped_column(String(40))
    date_limite: Mapped[dt.date] = mapped_column(Date)
    envoyee_le: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    recue_le: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    commentaire: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    relances: Mapped[list[str]] = mapped_column(JSONB, default=list)


class PermanentDocument(TrackedMixin, Base):
    """Document du dossier permanent d'un client (RCO-05), repris d'un exercice à l'autre ;
    sa date de validité permet de signaler les documents expirés (RCO-06)."""

    __tablename__ = "permanent_documents"

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    categorie: Mapped[str] = mapped_column(String(30))
    libelle: Mapped[str] = mapped_column(String(300))
    date_document: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    date_validite: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    commentaire: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class ChecklistAnswer(TrackedMixin, Base):
    """Réponse à un point de la check-list de révision d'une clôture (RCO-07)."""

    __tablename__ = "closing_checklist_answers"
    __table_args__ = (
        Index("uq_closing_checklist_point", "closing_id", "code", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    closing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("closings.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    statut: Mapped[str] = mapped_column(String(20))  # fait, sans_objet, anomalie
    commentaire: Mapped[str | None] = mapped_column(String(4000), nullable=True)


class AccountJustification(TrackedMixin, Base):
    """Justification d'un compte de bilan d'une clôture (RCO-09) et sa revue."""

    __tablename__ = "account_justifications"
    __table_args__ = (
        Index("uq_account_justifications", "audit_file_id", "compte", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    compte: Mapped[str] = mapped_column(String(30))
    montant_justifie: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    revue_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revue_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Solde revu : un solde modifié après la revue rend le compte de nouveau signalé.
    solde_revu: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    commentaire_revue: Mapped[str | None] = mapped_column(String(4000), nullable=True)


class FixedAsset(TrackedMixin, Base):
    """Immobilisation du tableau d'un client (RCO-11), reprise d'un exercice à l'autre ; un
    composant est rattaché à son ensemble (`composant_de`)."""

    __tablename__ = "fixed_assets"

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(300))
    composant_de: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fixed_assets.id"), nullable=True
    )
    compte_immobilisation: Mapped[str] = mapped_column(String(30))
    compte_amortissement: Mapped[str] = mapped_column(String(30))
    compte_dotation: Mapped[str] = mapped_column(String(30))
    date_mise_en_service: Mapped[dt.date] = mapped_column(Date)
    valeur_origine: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    mode: Mapped[str] = mapped_column(String(20))  # lineaire, degressif
    duree_annees: Mapped[int] = mapped_column(Integer)
    coefficient: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    date_cession: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    prix_cession: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)


class StockCount(TrackedMixin, Base):
    """Inventaire physique et entrées de stock d'une clôture (RCO-12)."""

    __tablename__ = "stock_counts"
    __table_args__ = (
        Index("uq_stock_counts_file", "audit_file_id", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    methode: Mapped[str] = mapped_column(String(10), default="cmp")  # cmp, peps
    inventaire: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    mouvements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    fichiers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Accrual(TrackedMixin, Base):
    """Élément de rattachement à l'exercice d'une clôture (RCO-13) : charge à payer, produit à
    recevoir, charge ou produit constaté d'avance."""

    __tablename__ = "accruals"

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    audit_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_files.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    libelle: Mapped[str] = mapped_column(String(300))
    compte_gestion: Mapped[str] = mapped_column(String(30))
    compte_tiers: Mapped[str] = mapped_column(String(30))
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # Assistant constaté d'avance : montant total et période couverte.
    montant_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    periode_debut: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    periode_fin: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
