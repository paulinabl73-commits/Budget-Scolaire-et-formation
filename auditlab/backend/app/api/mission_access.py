"""Restriction des droits par mission (section 2) : un auditeur ne voit que ses missions."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models.engagement import (
    Engagement,
    EngagementMember,
    EngagementStatus,
    MissionRole,
)
from app.models.user import User
from app.security.roles import Perm, Role, has_permission


def sees_all(user: User) -> bool:
    return has_permission(user.role, Perm.MISSIONS_READ_ALL)


def visible_engagements(user: User) -> Select[tuple[Engagement]]:
    query = select(Engagement).where(Engagement.deleted_at.is_(None))
    if sees_all(user):
        return query
    if not has_permission(user.role, Perm.MISSIONS_READ_OWN):
        return query.where(False)
    member_of = select(EngagementMember.engagement_id).where(
        EngagementMember.user_id == user.id, EngagementMember.deleted_at.is_(None)
    )
    return query.where(Engagement.id.in_(member_of))


def get_engagement(db: Session, engagement_id: uuid.UUID, user: User) -> Engagement:
    engagement = db.scalar(
        visible_engagements(user)
        .where(Engagement.id == engagement_id)
        .options(
            selectinload(Engagement.members).selectinload(EngagementMember.user),
            selectinload(Engagement.entity),
        )
        .execution_options(populate_existing=True)
    )
    if engagement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission introuvable")
    return engagement


def mission_role(engagement: Engagement, user: User) -> MissionRole | None:
    for m in engagement.members:
        if m.user_id == user.id:
            return MissionRole(m.role_mission)
    return None


def can_manage(engagement: Engagement, user: User) -> bool:
    """Directeur sur toutes les missions ; Chef de mission sur celles qu'il pilote ; Associé
    signataire sur celles qu'il supervise (droits du Directeur sur ses dossiers)."""
    if not has_permission(user.role, Perm.MISSIONS_MANAGE):
        return False
    role = mission_role(engagement, user)
    if user.role == Role.ASSOCIE.value and role == MissionRole.SUPERVISEUR:
        return True
    return sees_all(user) or role == MissionRole.CHEF


def require_manager(engagement: Engagement, user: User) -> None:
    if not can_manage(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de mission")


def require_member(engagement: Engagement, user: User) -> MissionRole:
    role = mission_role(engagement, user)
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'équipe de la mission")
    return role


def ensure_open(engagement: Engagement) -> None:
    if engagement.statut == EngagementStatus.CLOTUREE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mission clôturée : consultation uniquement")
