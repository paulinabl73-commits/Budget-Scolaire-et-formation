"""Circuit de signatures des papiers de travail (AUD-18).

Préparé → Revu → Approuvé, chaque signature horodatée et liée à l'empreinte de la version
signée. Séparation des tâches : le préparateur ne peut ni revoir ni approuver son papier.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import mission_role, sees_all
from app.models.engagement import Engagement, EngagementStatus, MissionRole
from app.models.user import User
from app.models.workpaper import (
    SIGNOFF_ORDER,
    Signoff,
    SignoffType,
    Workpaper,
    WorkpaperVersion,
)
from app.schemas_workpaper import SignoffIn, SignoffOut
from app.security.roles import Perm, can_review, has_permission

router = APIRouter(tags=["Signatures"])

# Contrôles supplémentaires avant une signature (ex. AUD-19 : notes de revue ouvertes).
SIGNOFF_GUARDS: dict[SignoffType, list[Callable[[Session, Workpaper], str | None]]] = {
    t: [] for t in SignoffType
}


def signoffs_by_workpaper(
    db: Session, ids: list[uuid.UUID], active_only: bool = True
) -> dict[uuid.UUID, list[Signoff]]:
    result: dict[uuid.UUID, list[Signoff]] = {i: [] for i in ids}
    if not ids:
        return result
    query = (
        select(Signoff)
        .where(Signoff.workpaper_id.in_(ids), Signoff.deleted_at.is_(None))
        .options(selectinload(Signoff.user))
        .order_by(Signoff.signed_at)
    )
    if active_only:
        query = query.where(Signoff.annule_le.is_(None))
    for s in db.scalars(query):
        result[s.workpaper_id].append(s)
    return result


def signoff_out(s: Signoff) -> SignoffOut:
    return SignoffOut(
        id=s.id,
        type=s.type,
        user_id=s.user_id,
        user_nom=s.user.nom,
        signed_at=s.signed_at,
        version=s.version,
        hash_contenu=s.hash_contenu,
        annule_le=s.annule_le,
        motif_annulation=s.motif_annulation,
    )


def status_of(active: list[Signoff]) -> str:
    done = {s.type for s in active}
    current = "brouillon"
    for step in SIGNOFF_ORDER:
        if step.value in done:
            current = step.value
    return current


def _preparer(active: list[Signoff]) -> uuid.UUID | None:
    return next((s.user_id for s in active if s.type == SignoffType.PREPARE), None)


def refusal(
    db: Session,
    wp: Workpaper,
    engagement: Engagement,
    user: User,
    kind: SignoffType,
    active: list[Signoff],
) -> str | None:
    """Motif pour lequel l'utilisateur ne peut pas apposer cette signature, ou None."""
    from app.api.workpapers import can_prepare

    if engagement.statut == EngagementStatus.CLOTUREE:
        return "Mission clôturée"
    done = {s.type for s in active}
    if kind.value in done:
        return "Étape déjà signée"
    role = mission_role(engagement, user)
    preparer = _preparer(active)
    if kind == SignoffType.PREPARE:
        if not can_prepare(engagement, user):
            return "Réservé aux auditeurs et au chef de la mission"
        if not wp.conclusion or not wp.evaluation:
            return "Conclusion et évaluation du contrôle requises avant signature"
    elif kind == SignoffType.REVU:
        if SignoffType.PREPARE.value not in done:
            return "Le papier doit d'abord être signé par son préparateur"
        reviewer = role in (MissionRole.CHEF, MissionRole.SUPERVISEUR) and (
            has_permission(user.role, Perm.WORKPAPERS_REVIEW)
            or has_permission(user.role, Perm.WORKPAPERS_APPROVE_FINAL)
        )
        if not reviewer:
            return "Réservé au chef de mission ou au superviseur"
        if not can_review(preparer, user.id):
            return "Séparation des tâches : le préparateur ne peut pas revoir son papier"
    else:
        if SignoffType.REVU.value not in done:
            return "Le papier doit d'abord être revu"
        approver = (
            role == MissionRole.CHEF and has_permission(user.role, Perm.WORKPAPERS_REVIEW)
        ) or (sees_all(user) and has_permission(user.role, Perm.WORKPAPERS_APPROVE_FINAL))
        if not approver:
            return "Réservé au chef de mission ou au Directeur"
        if not can_review(preparer, user.id):
            return "Séparation des tâches : le préparateur ne peut pas approuver son papier"
    for guard in SIGNOFF_GUARDS[kind]:
        if reason := guard(db, wp):
            return reason
    return None


def possible(
    db: Session, wp: Workpaper, engagement: Engagement, user: User, active: list[Signoff]
) -> tuple[list[SignoffType], dict[str, str]]:
    allowed, reasons = [], {}
    for kind in SIGNOFF_ORDER:
        reason = refusal(db, wp, engagement, user, kind, active)
        if reason is None:
            allowed.append(kind)
        else:
            reasons[kind.value] = reason
    return allowed, reasons


def current_hash(db: Session, wp: Workpaper) -> str:
    return (
        db.scalar(
            select(WorkpaperVersion.hash_contenu).where(
                WorkpaperVersion.workpaper_id == wp.id, WorkpaperVersion.version == wp.version
            )
        )
        or ""
    )


@router.post("/workpapers/{workpaper_id}/signoffs", response_model=SignoffOut, status_code=201)
def sign(workpaper_id: uuid.UUID, body: SignoffIn, user: CurrentUser, db: DbSession) -> SignoffOut:
    from app.api.workpapers import get_workpaper

    wp, engagement = get_workpaper(db, workpaper_id, user)
    active = signoffs_by_workpaper(db, [wp.id])[wp.id]
    if reason := refusal(db, wp, engagement, user, body.type, active):
        code = (
            status.HTTP_403_FORBIDDEN
            if reason.startswith(("Réservé", "Séparation"))
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(code, reason)
    signoff = Signoff(
        engagement_id=engagement.id,
        workpaper_id=wp.id,
        type=body.type.value,
        user_id=user.id,
        signed_at=datetime.now(UTC),
        version=wp.version,
        hash_contenu=current_hash(db, wp),
    )
    db.add(signoff)
    db.commit()
    db.refresh(signoff)
    return signoff_out(signoff)


@router.get("/workpapers/{workpaper_id}/signoffs", response_model=list[SignoffOut])
def history(workpaper_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[SignoffOut]:
    """Toutes les signatures, y compris celles annulées par une modification (AUD-20)."""
    from app.api.workpapers import get_workpaper

    wp, _ = get_workpaper(db, workpaper_id, user)
    return [signoff_out(s) for s in signoffs_by_workpaper(db, [wp.id], active_only=False)[wp.id]]


def invalidate(db: Session, wp: Workpaper, engagement: Engagement, actor: User, motif: str) -> int:
    """AUD-20 : toute modification après signature annule les signatures et prévient le
    réviseur. Renvoie le nombre de signatures annulées."""
    from app.notify import notify

    active = signoffs_by_workpaper(db, [wp.id])[wp.id]
    if not active:
        return 0
    now = datetime.now(UTC)
    for s in active:
        s.annule_le = now
        s.motif_annulation = motif
    recipients = {s.user_id for s in active if s.type != SignoffType.PREPARE}
    recipients |= {m.user_id for m in engagement.members if m.role_mission == MissionRole.CHEF}
    recipients.discard(actor.id)
    notify(
        db,
        recipients,
        "signature_annulee",
        f"{engagement.reference} · {wp.reference} modifié après signature",
        f"{actor.nom} a modifié le papier {wp.reference} « {wp.titre} » ({motif}). "
        f"Ses {len(active)} signature(s) sont annulées : une nouvelle revue est nécessaire.",
        lien=f"/missions/{engagement.id}/papiers/{wp.id}",
    )
    return len(active)
