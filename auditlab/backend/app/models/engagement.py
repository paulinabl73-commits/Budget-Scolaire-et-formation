import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TrackedMixin
from app.models.universe import AuditableEntity
from app.models.user import User


class EngagementStatus(StrEnum):
    """Cycle de vie d'une mission (AUD-07), dans l'ordre."""

    PLANIFIEE = "planifiee"
    PREPARATION = "preparation"
    TERRAIN = "terrain"
    REVUE = "revue"
    RAPPORT = "rapport"
    CLOTUREE = "cloturee"


STATUS_ORDER = list(EngagementStatus)


class MissionRole(StrEnum):
    CHEF = "chef_mission"
    AUDITEUR = "auditeur"
    DATA_ANALYST = "data_analyst"
    SUPERVISEUR = "superviseur"


class Engagement(TrackedMixin, Base):
    """Mission d'audit (AUD-06), créée depuis le plan ou ponctuellement."""

    __tablename__ = "engagements"

    reference: Mapped[str] = mapped_column(String(30), unique=True)
    titre: Mapped[str] = mapped_column(String(300))
    perimetre: Mapped[str | None] = mapped_column(Text, nullable=True)
    objectifs: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(20), default=EngagementStatus.PLANIFIEE.value)
    # « audit » ou « inspection_cipres » (CIP-08 : rapports provisoire et définitif d'inspection).
    mode: Mapped[str] = mapped_column(String(30), default="audit", server_default="audit")
    budget_jours: Mapped[float] = mapped_column(Float)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auditable_entities.id"), nullable=True, index=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audit_plans.id"), nullable=True, index=True
    )
    plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plan_items.id"), nullable=True, index=True
    )
    # AUD-22 : horodatage et auteur de la clôture (mission alors figée).
    cloturee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloturee_par: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    entity: Mapped[AuditableEntity | None] = relationship(viewonly=True)
    members: Mapped[list["EngagementMember"]] = relationship(
        primaryjoin="and_(Engagement.id == EngagementMember.engagement_id, "
        "EngagementMember.deleted_at.is_(None))",
        viewonly=True,
    )


class EngagementMember(TrackedMixin, Base):
    """Équipe de la mission ; c'est elle qui restreint l'accès des auditeurs."""

    __tablename__ = "engagement_members"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role_mission: Mapped[str] = mapped_column(String(20))

    user: Mapped[User] = relationship(foreign_keys=[user_id], viewonly=True)


class TimeActivity(StrEnum):
    PREPARATION = "preparation"
    TERRAIN = "terrain"
    REVUE = "revue"
    RAPPORT = "rapport"
    AUTRE = "autre"


class TimeEntry(TrackedMixin, Base):
    """Temps passé par un membre de l'équipe sur la mission (AUD-08)."""

    __tablename__ = "time_entries"

    engagement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("engagements.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    heures: Mapped[float] = mapped_column(Float)
    activite: Mapped[str] = mapped_column(String(20))
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(foreign_keys=[user_id], viewonly=True)
