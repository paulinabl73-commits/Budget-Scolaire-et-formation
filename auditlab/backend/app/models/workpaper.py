"""Papiers de travail (AUD-13 à AUD-20)."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
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
