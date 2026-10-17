"""Notes de revue ancrées sur un passage, avec statut Ouverte, Répondue, Clôturée (AUD-19)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.engagement_status import GUARDS, ON_ENTER
from app.api.mission_access import ensure_open, get_engagement, mission_role, sees_all
from app.api.signoffs import SIGNOFF_GUARDS
from app.models.engagement import Engagement, EngagementStatus, MissionRole
from app.models.user import User
from app.models.workpaper import (
    ReviewNote,
    ReviewNoteReply,
    ReviewNoteStatus,
    SignoffType,
    Workpaper,
)
from app.schemas_workpaper import ReplyIn, ReplyOut, ReviewNoteIn, ReviewNoteOut
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Notes de revue"])


def is_reviewer(engagement: Engagement, user: User) -> bool:
    role = mission_role(engagement, user)
    if role in (MissionRole.CHEF, MissionRole.SUPERVISEUR):
        return True
    return sees_all(user) and has_permission(user.role, Perm.WORKPAPERS_APPROVE_FINAL)


def notes_out(db: Session, notes: list[ReviewNote]) -> list[ReviewNoteOut]:
    if not notes:
        return []
    ids = [n.id for n in notes]
    names = dict(db.execute(select(User.id, User.nom)).all())
    refs = dict(
        db.execute(
            select(Workpaper.id, Workpaper.reference).where(
                Workpaper.id.in_({n.workpaper_id for n in notes})
            )
        ).all()
    )
    replies: dict[uuid.UUID, list[ReplyOut]] = {i: [] for i in ids}
    for r in db.scalars(
        select(ReviewNoteReply)
        .where(ReviewNoteReply.note_id.in_(ids), ReviewNoteReply.deleted_at.is_(None))
        .order_by(ReviewNoteReply.created_at)
    ):
        replies[r.note_id].append(
            ReplyOut(
                id=r.id, texte=r.texte, auteur=names.get(r.created_by), created_at=r.created_at
            )
        )
    return [
        ReviewNoteOut(
            id=n.id,
            workpaper_id=n.workpaper_id,
            workpaper_reference=refs.get(n.workpaper_id),
            texte=n.texte,
            ancre=n.ancre,
            statut=n.statut,
            auteur=names.get(n.created_by),
            created_by=n.created_by,
            created_at=n.created_at,
            cloturee_le=n.cloturee_le,
            reponses=replies[n.id],
        )
        for n in notes
    ]


def open_notes_count(
    db: Session, *, workpaper_id: uuid.UUID | None = None, engagement_id: uuid.UUID | None = None
) -> int:
    query = (
        select(func.count())
        .select_from(ReviewNote)
        .where(
            ReviewNote.deleted_at.is_(None), ReviewNote.statut != ReviewNoteStatus.CLOTUREE.value
        )
    )
    if workpaper_id:
        query = query.where(ReviewNote.workpaper_id == workpaper_id)
    if engagement_id:
        query = query.where(ReviewNote.engagement_id == engagement_id)
    return db.scalar(query) or 0


def _no_open_notes(db: Session, wp: Workpaper) -> str | None:
    n = open_notes_count(db, workpaper_id=wp.id)
    return f"{n} note(s) de revue non clôturée(s)" if n else None


# L'approbation d'un papier exige que toutes ses notes de revue soient clôturées.
SIGNOFF_GUARDS[SignoffType.APPROUVE].append(_no_open_notes)


def _note(db: Session, note_id: uuid.UUID, user: User) -> tuple[ReviewNote, Engagement]:
    note = db.scalar(
        select(ReviewNote).where(ReviewNote.id == note_id, ReviewNote.deleted_at.is_(None))
    )
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note de revue introuvable")
    return note, get_engagement(db, note.engagement_id, user)


@router.get("/workpapers/{workpaper_id}/review-notes", response_model=list[ReviewNoteOut])
def list_notes(workpaper_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[ReviewNoteOut]:
    from app.api.workpapers import get_workpaper

    wp, _ = get_workpaper(db, workpaper_id, user)
    notes = list(
        db.scalars(
            select(ReviewNote)
            .where(ReviewNote.workpaper_id == wp.id, ReviewNote.deleted_at.is_(None))
            .order_by(ReviewNote.created_at)
        )
    )
    return notes_out(db, notes)


@router.get("/engagements/{engagement_id}/review-notes", response_model=list[ReviewNoteOut])
def mission_notes(
    engagement_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    statut: ReviewNoteStatus | None = None,
) -> list[ReviewNoteOut]:
    engagement = get_engagement(db, engagement_id, user)
    query = select(ReviewNote).where(
        ReviewNote.engagement_id == engagement.id, ReviewNote.deleted_at.is_(None)
    )
    if statut:
        query = query.where(ReviewNote.statut == statut.value)
    return notes_out(db, list(db.scalars(query.order_by(ReviewNote.created_at))))


@router.post(
    "/workpapers/{workpaper_id}/review-notes", response_model=ReviewNoteOut, status_code=201
)
def create_note(
    workpaper_id: uuid.UUID, body: ReviewNoteIn, user: CurrentUser, db: DbSession
) -> ReviewNoteOut:
    from app.api.workpapers import get_workpaper

    wp, engagement = get_workpaper(db, workpaper_id, user)
    ensure_open(engagement)
    if not is_reviewer(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux réviseurs de la mission")
    note = ReviewNote(
        engagement_id=engagement.id,
        workpaper_id=wp.id,
        texte=body.texte,
        ancre=body.ancre.model_dump(),
        statut=ReviewNoteStatus.OUVERTE.value,
    )
    db.add(note)
    db.commit()
    return notes_out(db, [note])[0]


@router.post("/review-notes/{note_id}/replies", response_model=ReviewNoteOut, status_code=201)
def reply(note_id: uuid.UUID, body: ReplyIn, user: CurrentUser, db: DbSession) -> ReviewNoteOut:
    """Réponse d'un membre de l'équipe ; la note passe à « Répondue » si l'auteur n'est pas
    son réviseur."""
    note, engagement = _note(db, note_id, user)
    ensure_open(engagement)
    if mission_role(engagement, user) is None and not is_reviewer(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'équipe de la mission")
    if note.statut == ReviewNoteStatus.CLOTUREE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Note clôturée : rouvrez-la d'abord")
    db.add(ReviewNoteReply(engagement_id=engagement.id, note_id=note.id, texte=body.texte))
    if user.id != note.created_by:
        note.statut = ReviewNoteStatus.REPONDUE.value
    db.commit()
    return notes_out(db, [note])[0]


def _set_closed(db: Session, note_id: uuid.UUID, user: User, closed: bool) -> ReviewNoteOut:
    note, engagement = _note(db, note_id, user)
    ensure_open(engagement)
    if not is_reviewer(engagement, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seul un réviseur clôture ou rouvre une note"
        )
    if closed:
        note.statut = ReviewNoteStatus.CLOTUREE.value
        note.cloturee_par = user.id
        note.cloturee_le = datetime.now(UTC)
    else:
        note.statut = ReviewNoteStatus.OUVERTE.value
        note.cloturee_par = None
        note.cloturee_le = None
    db.commit()
    return notes_out(db, [note])[0]


@router.post("/review-notes/{note_id}/close", response_model=ReviewNoteOut)
def close(note_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ReviewNoteOut:
    return _set_closed(db, note_id, user, True)


@router.post("/review-notes/{note_id}/reopen", response_model=ReviewNoteOut)
def reopen(note_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ReviewNoteOut:
    return _set_closed(db, note_id, user, False)


def _mission_notes_closed(db: Session, engagement: Engagement) -> str | None:
    """AUD-21 : une mission ne passe en Rapport que si toutes ses notes sont clôturées."""
    n = open_notes_count(db, engagement_id=engagement.id)
    return f"{n} note(s) de revue non clôturée(s) dans la mission" if n else None


GUARDS[EngagementStatus.RAPPORT].append(_mission_notes_closed)


def _ready_to_close(db: Session, engagement: Engagement) -> str | None:
    """Dossier complet avant clôture : papiers approuvés et notes de revue clôturées."""
    from app.api.signoffs import signoffs_by_workpaper, status_of

    if reason := _mission_notes_closed(db, engagement):
        return reason
    papers = list(
        db.scalars(
            select(Workpaper).where(
                Workpaper.engagement_id == engagement.id, Workpaper.deleted_at.is_(None)
            )
        )
    )
    active = signoffs_by_workpaper(db, [w.id for w in papers])
    pending = [w.reference for w in papers if status_of(active[w.id]) != "approuve"]
    if pending:
        return "Papiers de travail non approuvés : " + ", ".join(sorted(pending))
    return None


def _lock(db: Session, engagement: Engagement, user: User) -> None:
    """À la clôture : horodatage, auteur et date du dernier audit de l'entité (AUD-02)."""
    from app.models.universe import AuditableEntity

    engagement.cloturee_le = datetime.now(UTC)
    engagement.cloturee_par = user.id
    if engagement.entity_id:
        entity = db.get(AuditableEntity, engagement.entity_id)
        if entity and (
            entity.date_dernier_audit is None or entity.date_dernier_audit < engagement.date_fin
        ):
            entity.date_dernier_audit = engagement.date_fin


GUARDS[EngagementStatus.CLOTUREE].append(_ready_to_close)
ON_ENTER[EngagementStatus.CLOTUREE].append(_lock)
