import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


class EntityType(StrEnum):
    DIRECTION = "direction"
    FILIALE = "filiale"
    PROCESSUS = "processus"
    SYSTEME = "systeme"


class AuditableEntity(TrackedMixin, Base):
    """Entité de l'univers d'audit, organisée en arborescence (AUD-01)."""

    __tablename__ = "auditable_entities"

    nom: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auditable_entities.id"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_dernier_audit: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Score du dernier RiskAssessment (AUD-02), recopié pour trier et filtrer sans jointure.
    score_risque: Mapped[float | None] = mapped_column(Float, nullable=True)
