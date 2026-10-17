"""Papiers de travail (AUD-13 à AUD-20)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TrackedMixin
from app.models.user import User


class ControlAssessment(StrEnum):
    """Évaluation du contrôle portée par le papier de travail (AUD-13)."""

    EFFICACE = "efficace"
    PARTIELLEMENT_EFFICACE = "partiellement_efficace"
    INEFFICACE = "inefficace"


class Workpaper(TrackedMixin, Base):
    __tablename__ = "workpapers"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("procedures.id"), nullable=True, index=True
    )
    reference: Mapped[str] = mapped_column(String(30))
    titre: Mapped[str] = mapped_column(String(300))
    objectif: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Document riche (format ProseMirror / TipTap) : paragraphes, tableaux, images, liens.
    travaux: Mapped[dict[str, Any]] = mapped_column(JSONB)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Numéro de la version courante (AUD-17), incrémenté à chaque enregistrement.
    version: Mapped[int] = mapped_column(Integer, default=1)


class Attachment(TrackedMixin, Base):
    """Pièce jointe d'un papier de travail (AUD-15), stockée hors base et jamais réécrite."""

    __tablename__ = "attachments"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    workpaper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workpapers.id"), index=True)
    nom_fichier: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    taille: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    # Un même nom déposé plusieurs fois sur un papier forme des versions successives.
    version: Mapped[int] = mapped_column(Integer, default=1)


class Tickmark(TrackedMixin, Base):
    """Marque de révision paramétrable insérée dans les travaux (AUD-16)."""

    __tablename__ = "tickmarks"

    symbole: Mapped[str] = mapped_column(String(4), unique=True)
    libelle: Mapped[str] = mapped_column(String(200))
    couleur: Mapped[str] = mapped_column(String(7), default="#1f5fa8")
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkpaperVersion(Base):
    """Version figée d'un papier de travail (AUD-17), en ajout seul (déclencheur SQL)."""

    __tablename__ = "workpaper_versions"
    __table_args__ = (UniqueConstraint("workpaper_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workpaper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workpapers.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    contenu: Mapped[dict[str, Any]] = mapped_column(JSONB)
    hash_contenu: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SignoffType(StrEnum):
    PREPARE = "prepare"
    REVU = "revu"
    APPROUVE = "approuve"


SIGNOFF_ORDER = [SignoffType.PREPARE, SignoffType.REVU, SignoffType.APPROUVE]


class Signoff(TrackedMixin, Base):
    """Signature horodatée d'un papier (AUD-18), liée à l'empreinte de la version signée."""

    __tablename__ = "signoffs"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    workpaper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workpapers.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)
    hash_contenu: Mapped[str] = mapped_column(String(64))
    # AUD-20 : une modification après signature annule la signature (jamais supprimée).
    annule_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motif_annulation: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user: Mapped[User] = relationship(foreign_keys=[user_id], viewonly=True)


class ReviewNoteStatus(StrEnum):
    OUVERTE = "ouverte"
    REPONDUE = "repondue"
    CLOTUREE = "cloturee"


class ReviewNote(TrackedMixin, Base):
    """Note de revue ancrée sur un passage d'un papier (AUD-19)."""

    __tablename__ = "review_notes"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    workpaper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workpapers.id"), index=True)
    texte: Mapped[str] = mapped_column(Text)
    # Ancre : champ concerné et passage cité, ex. {"champ": "travaux", "citation": "…"}.
    ancre: Mapped[dict[str, Any]] = mapped_column(JSONB)
    statut: Mapped[str] = mapped_column(String(20), default=ReviewNoteStatus.OUVERTE.value)
    cloturee_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cloturee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewNoteReply(TrackedMixin, Base):
    __tablename__ = "review_note_replies"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_notes.id"), index=True)
    texte: Mapped[str] = mapped_column(Text)
