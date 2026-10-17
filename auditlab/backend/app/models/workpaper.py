"""Papiers de travail (AUD-13 à AUD-20)."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


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
