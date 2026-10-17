import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


class Axis(StrEnum):
    IMPACT = "impact"
    PROBABILITE = "probabilite"
    AUTRE = "autre"


class CriterionMode(StrEnum):
    NOTE = "note"  # note saisie par l'évaluateur
    ANCIENNETE = "anciennete"  # note déduite de la date du dernier audit


class RiskCriterion(TrackedMixin, Base):
    """Critère d'évaluation paramétrable (AUD-02)."""

    __tablename__ = "risk_criteria"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    libelle: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    axe: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20), default=CriterionMode.NOTE.value)
    poids: Mapped[float] = mapped_column(Float, default=1.0)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class RiskAssessment(TrackedMixin, Base):
    """Évaluation datée d'une entité ; les critères sont figés dans `criteres` (AUD-02)."""

    __tablename__ = "risk_assessments"

    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("auditable_entities.id"), index=True)
    date_evaluation: Mapped[date] = mapped_column(Date)
    criteres: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    score: Mapped[float] = mapped_column(Float)
    impact: Mapped[float | None] = mapped_column(Float, nullable=True)
    probabilite: Mapped[float | None] = mapped_column(Float, nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
