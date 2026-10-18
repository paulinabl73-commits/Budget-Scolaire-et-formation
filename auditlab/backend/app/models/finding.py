"""Module 3 : constats, recommandations et suivi des plans d'action."""

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


class Criticality(StrEnum):
    """CON-02 : quatre niveaux, du plus faible au plus grave."""

    FAIBLE = "faible"
    MOYENNE = "moyenne"
    ELEVEE = "elevee"
    CRITIQUE = "critique"


CRITICALITY_ORDER = list(Criticality)


class FindingStatus(StrEnum):
    BROUILLON = "brouillon"  # rédaction par l'équipe
    ENVOYE = "envoye"  # phase contradictoire : en attente de la réponse de l'audité (CON-04)
    REPONDU = "repondu"  # l'audité a répondu et proposé un plan d'action
    VALIDE = "valide"  # constat définitif, repris dans le rapport


class Finding(TrackedMixin, Base):
    """Fiche constat en cinq volets (CON-01)."""

    __tablename__ = "findings"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    reference: Mapped[str] = mapped_column(String(20))
    titre: Mapped[str] = mapped_column(String(300))
    critere: Mapped[str | None] = mapped_column(Text, nullable=True)  # la règle attendue
    constat: Mapped[str | None] = mapped_column(Text, nullable=True)  # les faits
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    consequence: Mapped[str | None] = mapped_column(Text, nullable=True)  # le risque
    recommandation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # CON-02 : criticité et rattachements (copies de mission du risque et du contrôle).
    criticite: Mapped[str] = mapped_column(String(20), default=Criticality.MOYENNE.value)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risks.id"), nullable=True)
    control_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("controls.id"), nullable=True)
    workpaper_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # CON-04 : phase contradictoire.
    statut: Mapped[str] = mapped_column(String(20), default=FindingStatus.BROUILLON.value)
    audite_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    envoye_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_limite_reponse: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    reponse_position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reponse_commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    repondu_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repondu_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    valide_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    commentaire_validation: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class EvidenceType(StrEnum):
    PAPIER = "papier"  # papier de travail
    PIECE_JOINTE = "piece_jointe"  # pièce jointe d'un papier
    TABLE = "table"  # résultat d'analyse
    LIGNES = "lignes"  # lignes d'anomalie extraites d'une table (DAT-31)


class FindingEvidence(TrackedMixin, Base):
    """Preuve rattachée à un constat (CON-03), avec l'empreinte de l'élément au moment du lien."""

    __tablename__ = "finding_evidences"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workpapers.id"), nullable=True
    )
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    empreinte: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extrait: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)


class ActionPlanStatus(StrEnum):
    """CON-05 : statuts d'un plan d'action."""

    A_LANCER = "a_lancer"
    EN_COURS = "en_cours"
    REALISE = "realise"  # déclaré réalisé par le responsable, à vérifier
    VERIFIE = "verifie"  # vérifié par l'audit (CON-07)
    RISQUE_ACCEPTE = "risque_accepte"


CLOSED_PLAN_STATUSES = (ActionPlanStatus.VERIFIE.value, ActionPlanStatus.RISQUE_ACCEPTE.value)


class ActionPlan(TrackedMixin, Base):
    """Plan d'action d'un constat (CON-05).

    Pas de colonne engagement_id : le suivi des plans se poursuit après la clôture de la
    mission (norme IIA 2500), alors que la mission clôturée est verrouillée.
    """

    __tablename__ = "action_plans"

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    responsable_nom: Mapped[str | None] = mapped_column(String(200), nullable=True)
    echeance: Mapped[dt.date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(20), default=ActionPlanStatus.A_LANCER.value)
    propose_par_audite: Mapped[bool] = mapped_column(default=False)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    verifie_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verifie_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # CON-06 : relances envoyées ({"type": "j15" | "echeance" | "retard", "date": …}).
    relances: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class PlanEvidence(TrackedMixin, Base):
    """Justificatif déposé pour un plan d'action (CON-07), conservé avec son empreinte."""

    __tablename__ = "plan_evidences"

    action_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("action_plans.id"), index=True)
    nom_fichier: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    taille: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)


class Postponement(TrackedMixin, Base):
    """Demande de report d'échéance d'un plan (CON-08), décidée par le chef de mission."""

    __tablename__ = "plan_postponements"

    action_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("action_plans.id"), index=True)
    ancienne_echeance: Mapped[dt.date] = mapped_column(Date)
    nouvelle_echeance: Mapped[dt.date] = mapped_column(Date)
    motif: Mapped[str] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(20), default="demande")  # accepte, refuse
    decide_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decide_le: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commentaire_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    relances_precedentes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class InspectionReport(TrackedMixin, Base):
    """Rapport d'une mission d'inspection CIPRES (CIP-08) : provisoire puis définitif. Son
    contenu est figé à l'émission (blocs et empreinte) ; les exports en sont tirés."""

    __tablename__ = "inspection_reports"
    __table_args__ = (
        Index("uq_inspection_reports_version", "engagement_id", "version", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    version: Mapped[str] = mapped_column(String(20))  # provisoire, definitif
    titre: Mapped[str] = mapped_column(String(300))
    blocs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    sha256: Mapped[str] = mapped_column(String(64))
    emis_le: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    emis_par: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    destinataire: Mapped[str | None] = mapped_column(String(300), nullable=True)
    date_limite_reponse: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # Réponse générale de l'organisme contrôlé au rapport provisoire.
    reponse_organisme: Mapped[str | None] = mapped_column(Text, nullable=True)
    reponse_recue_le: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class FollowUpStatus(StrEnum):
    MISE_EN_OEUVRE = "mise_en_oeuvre"
    PARTIELLE = "partielle"
    NON_MISE_EN_OEUVRE = "non_mise_en_oeuvre"
    SANS_OBJET = "sans_objet"


class RecommendationFollowUp(TrackedMixin, Base):
    """Suivi, lors d'une inspection, d'une recommandation d'une inspection précédente."""

    __tablename__ = "recommendation_follow_ups"
    __table_args__ = (
        Index("uq_recommendation_follow_ups", "engagement_id", "finding_id", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )  # fmt: skip

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), index=True)
    statut: Mapped[str] = mapped_column(String(30))
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
