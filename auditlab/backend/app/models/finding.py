"""Module 3 : constats, recommandations et suivi des plans d'action."""

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
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
