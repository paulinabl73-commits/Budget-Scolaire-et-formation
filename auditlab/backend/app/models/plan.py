import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TrackedMixin
from app.models.universe import AuditableEntity
from app.models.user import User


class PlanStatus(StrEnum):
    BROUILLON = "brouillon"
    VALIDE = "valide"
    REMPLACE = "remplace"


class AuditPlan(TrackedMixin, Base):
    """Plan d'audit annuel (AUD-04) ; chaque version est un enregistrement distinct (AUD-05)."""

    __tablename__ = "audit_plans"
    __table_args__ = (UniqueConstraint("annee", "version", name="uq_audit_plans_annee_version"),)

    annee: Mapped[int] = mapped_column(Integer, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    statut: Mapped[str] = mapped_column(String(20), default=PlanStatus.BROUILLON.value)
    capacite_jours: Mapped[float | None] = mapped_column(Float, nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AUD-05 : validation par le Directeur d'audit et filiation des versions.
    valide_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version_precedente_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audit_plans.id"), nullable=True
    )

    items: Mapped[list["PlanItem"]] = relationship(
        back_populates="plan",
        primaryjoin="and_(AuditPlan.id == PlanItem.plan_id, PlanItem.deleted_at.is_(None))",
        order_by="PlanItem.periode_debut",
        viewonly=True,
    )
    validator: Mapped[User | None] = relationship(foreign_keys=[valide_par], viewonly=True)


class PlanItem(TrackedMixin, Base):
    """Mission prévue au plan : une entité, un budget en jours-homme, une période (AUD-04)."""

    __tablename__ = "plan_items"

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_plans.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("auditable_entities.id"), index=True)
    titre: Mapped[str] = mapped_column(String(300))
    budget_jours: Mapped[float] = mapped_column(Float)
    periode_debut: Mapped[date] = mapped_column(Date)
    periode_fin: Mapped[date] = mapped_column(Date)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[AuditPlan] = relationship(back_populates="items", viewonly=True)
    entity: Mapped[AuditableEntity] = relationship(viewonly=True)
