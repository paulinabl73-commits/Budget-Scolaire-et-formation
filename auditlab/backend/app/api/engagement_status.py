"""Cycle de vie des missions (AUD-07).

Une mission avance d'un statut à la fois et peut revenir d'un cran (par exemple de Revue à
Terrain pour compléter des travaux), sauf une fois clôturée. Des contrôles de passage peuvent
bloquer un statut cible : les lots suivants les enregistrent dans GUARDS (AUD-21, AUD-22).
"""

import uuid
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import can_manage, get_engagement
from app.models.audit_log import AuditLog
from app.models.engagement import STATUS_ORDER, Engagement, EngagementStatus
from app.models.user import User
from app.schemas_mission import EngagementOut, StatusChangeOut, StatusIn, TransitionOut

router = APIRouter(prefix="/engagements", tags=["Missions"])

Guard = Callable[[Session, Engagement], str | None]
GUARDS: dict[EngagementStatus, list[Guard]] = {s: [] for s in EngagementStatus}
# Actions exécutées après le changement de statut (ex. verrouillage à la clôture).
ON_ENTER: dict[EngagementStatus, list[Callable[[Session, Engagement, User], None]]] = {
    s: [] for s in EngagementStatus
}


def neighbours(current: EngagementStatus) -> list[tuple[EngagementStatus, str]]:
    if current == EngagementStatus.CLOTUREE:
        return []
    i = STATUS_ORDER.index(current)
    result = []
    if i + 1 < len(STATUS_ORDER):
        result.append((STATUS_ORDER[i + 1], "suivant"))
    if i > 0:
        result.append((STATUS_ORDER[i - 1], "precedent"))
    return result


def blocking_reason(db: Session, engagement: Engagement, target: EngagementStatus) -> str | None:
    for guard in GUARDS[target]:
        if reason := guard(db, engagement):
            return reason
    return None


def allowed_transitions(db: Session, engagement: Engagement, user: User) -> list[TransitionOut]:
    if not can_manage(engagement, user):
        return []
    return [
        TransitionOut(
            statut=target,
            sens=sens,
            motif_blocage=blocking_reason(db, engagement, target) if sens == "suivant" else None,
        )
        for target, sens in neighbours(EngagementStatus(engagement.statut))
    ]


@router.post("/{engagement_id}/status", response_model=EngagementOut)
def change_status(
    engagement_id: uuid.UUID, body: StatusIn, user: CurrentUser, db: DbSession
) -> EngagementOut:
    from app.api.engagements import engagement_out

    engagement = get_engagement(db, engagement_id, user)
    if not can_manage(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de mission")
    targets = dict(neighbours(EngagementStatus(engagement.statut)))
    if body.statut not in targets:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Passage impossible de « {engagement.statut} » à « {body.statut.value} »",
        )
    if targets[body.statut] == "suivant" and (
        reason := blocking_reason(db, engagement, body.statut)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    engagement.statut = body.statut.value
    for action in ON_ENTER[body.statut]:
        action(db, engagement, user)
    db.commit()
    return engagement_out(db, get_engagement(db, engagement.id, user), user)


@router.get("/{engagement_id}/status-history", response_model=list[StatusChangeOut])
def status_history(
    engagement_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[StatusChangeOut]:
    """Historique des statuts, lu dans le journal d'audit (source unique et inaltérable)."""
    engagement = get_engagement(db, engagement_id, user)
    rows = db.execute(
        select(AuditLog, User.nom)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(
            AuditLog.object_type == "Engagement",
            AuditLog.object_id == str(engagement.id),
            AuditLog.action == "update",
        )
        .order_by(AuditLog.seq)
    ).all()
    return [
        StatusChangeOut(
            horodatage=log.horodatage,
            utilisateur=nom,
            avant=log.avant["statut"],
            apres=log.apres["statut"],
        )
        for log, nom in rows
        if log.apres and "statut" in log.apres
    ]
