"""Papiers de travail (AUD-13)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import can_manage, ensure_open, get_engagement, mission_role
from app.api.program import mission_procedure
from app.models.engagement import Engagement, MissionRole
from app.models.program import Procedure
from app.models.user import User
from app.models.workpaper import Workpaper
from app.richtext import EMPTY_DOC, InvalidDocument, validate_doc
from app.schemas_workpaper import WorkpaperIn, WorkpaperOut, WorkpaperSummary, WorkpaperUpdate
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Papiers de travail"])

PREPARER_ROLES = {MissionRole.AUDITEUR, MissionRole.CHEF}


def can_prepare(engagement: Engagement, user: User) -> bool:
    """Rédaction : auditeurs et chef de la mission (matrice section 2 : l'auditeur prépare)."""
    role = mission_role(engagement, user)
    return role in PREPARER_ROLES and (
        has_permission(user.role, Perm.WORKPAPERS_PREPARE)
        or has_permission(user.role, Perm.WORKPAPERS_REVIEW)
    )


def get_workpaper(db: Session, workpaper_id: uuid.UUID, user: User) -> tuple[Workpaper, Engagement]:
    wp = db.scalar(
        select(Workpaper).where(Workpaper.id == workpaper_id, Workpaper.deleted_at.is_(None))
    )
    if wp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Papier de travail introuvable")
    engagement = get_engagement(db, wp.engagement_id, user)  # 404 si la mission est invisible
    if not has_permission(user.role, Perm.WORKPAPERS_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    return wp, engagement


def require_preparer(engagement: Engagement, user: User) -> None:
    ensure_open(engagement)
    if not can_prepare(engagement, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux auditeurs et au chef de la mission"
        )


def _check_reference(
    db: Session, engagement: Engagement, reference: str, exclude: uuid.UUID | None = None
) -> None:
    query = select(Workpaper.id).where(
        Workpaper.engagement_id == engagement.id,
        Workpaper.reference == reference,
        Workpaper.deleted_at.is_(None),
    )
    if exclude:
        query = query.where(Workpaper.id != exclude)
    if db.scalar(query):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"La référence {reference} existe déjà dans la mission"
        )


def _procedure_refs(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    return dict(
        db.execute(select(Procedure.id, Procedure.reference).where(Procedure.id.in_(ids))).all()
    )


def summary(wp: Workpaper, refs: dict[uuid.UUID, str | None]) -> dict:
    return {
        **{k: getattr(wp, k) for k in WorkpaperSummary.model_fields if hasattr(wp, k)},
        "procedure_reference": refs.get(wp.procedure_id) if wp.procedure_id else None,
    }


def workpaper_out(db: Session, wp: Workpaper, engagement: Engagement, user: User) -> WorkpaperOut:
    data = summary(wp, _procedure_refs(db, [wp.procedure_id] if wp.procedure_id else []))
    return WorkpaperOut.model_validate(
        {
            **data,
            "objectif": wp.objectif,
            "travaux": wp.travaux,
            "conclusion": wp.conclusion,
            "peut_modifier": engagement.statut != "cloturee" and can_prepare(engagement, user),
        }
    )


def _check_doc(db: Session, doc: dict | None, workpaper_id: uuid.UUID | None = None) -> None:
    if doc is None:
        return
    from app.models.workpaper import Attachment

    allowed: set[str] = set()
    if workpaper_id:
        allowed = {
            str(i)
            for i in db.scalars(
                select(Attachment.id).where(
                    Attachment.workpaper_id == workpaper_id, Attachment.deleted_at.is_(None)
                )
            )
        }
    try:
        validate_doc(doc, allowed)
    except InvalidDocument as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/engagements/{engagement_id}/workpapers", response_model=list[WorkpaperSummary])
def list_workpapers(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict]:
    engagement = get_engagement(db, engagement_id, user)
    if not has_permission(user.role, Perm.WORKPAPERS_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    rows = list(
        db.scalars(
            select(Workpaper)
            .where(Workpaper.engagement_id == engagement.id, Workpaper.deleted_at.is_(None))
            .order_by(Workpaper.reference)
        )
    )
    refs = _procedure_refs(db, [w.procedure_id for w in rows if w.procedure_id])
    return [summary(w, refs) for w in rows]


@router.post(
    "/engagements/{engagement_id}/workpapers", response_model=WorkpaperOut, status_code=201
)
def create_workpaper(
    engagement_id: uuid.UUID, body: WorkpaperIn, user: CurrentUser, db: DbSession
) -> WorkpaperOut:
    engagement = get_engagement(db, engagement_id, user)
    require_preparer(engagement, user)
    _check_reference(db, engagement, body.reference)
    _check_doc(db, body.travaux)
    if body.procedure_id:
        mission_procedure(db, engagement, body.procedure_id)
    wp = Workpaper(
        engagement_id=engagement.id,
        procedure_id=body.procedure_id,
        reference=body.reference,
        titre=body.titre,
        objectif=body.objectif,
        travaux=body.travaux or EMPTY_DOC,
        conclusion=body.conclusion,
        evaluation=body.evaluation.value if body.evaluation else None,
        version=1,
    )
    db.add(wp)
    db.commit()
    return workpaper_out(db, wp, engagement, user)


@router.get("/workpapers/{workpaper_id}", response_model=WorkpaperOut)
def read_workpaper(workpaper_id: uuid.UUID, user: CurrentUser, db: DbSession) -> WorkpaperOut:
    wp, engagement = get_workpaper(db, workpaper_id, user)
    return workpaper_out(db, wp, engagement, user)


def apply_update(db: Session, wp: Workpaper, engagement: Engagement, body: WorkpaperUpdate) -> bool:
    """Applique les changements ; renvoie True si le contenu a réellement changé."""
    changes = body.model_dump(mode="json", exclude_unset=True)
    if changes.get("reference"):
        _check_reference(db, engagement, changes["reference"], exclude=wp.id)
    _check_doc(db, changes.get("travaux"), wp.id)
    if changes.get("procedure_id"):
        mission_procedure(db, engagement, uuid.UUID(changes["procedure_id"]))
    changed = False
    for key, value in changes.items():
        if value is None and key in ("reference", "titre", "travaux"):
            continue
        if key == "procedure_id" and value is not None:
            value = uuid.UUID(value)
        if getattr(wp, key) != value:
            setattr(wp, key, value)
            changed = True
    if changed:
        wp.version += 1
    return changed


@router.patch("/workpapers/{workpaper_id}", response_model=WorkpaperOut)
def update_workpaper(
    workpaper_id: uuid.UUID, body: WorkpaperUpdate, user: CurrentUser, db: DbSession
) -> WorkpaperOut:
    wp, engagement = get_workpaper(db, workpaper_id, user)
    require_preparer(engagement, user)
    apply_update(db, wp, engagement, body)
    db.commit()
    return workpaper_out(db, wp, engagement, user)


@router.delete("/workpapers/{workpaper_id}", status_code=204)
def delete_workpaper(workpaper_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    wp, engagement = get_workpaper(db, workpaper_id, user)
    ensure_open(engagement)
    if not (can_manage(engagement, user) or wp.created_by == user.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seuls son auteur et le chef de mission suppriment un papier"
        )
    wp.deleted_at = datetime.now(UTC)
    wp.deleted_by = user.id
    db.commit()
