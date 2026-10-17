"""Temps passé par auditeur et par mission, comparé au budget (AUD-08)."""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import ColumnElement, func, select

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import can_manage, ensure_open, get_engagement, require_member
from app.config import get_settings
from app.models.engagement import TimeEntry
from app.models.user import User
from app.schemas_mission import (
    TimeEntryIn,
    TimeEntryOut,
    TimeEntryUpdate,
    TimeLine,
    TimeSummary,
)

router = APIRouter(prefix="/engagements", tags=["Temps"])


def _active() -> ColumnElement[bool]:
    return TimeEntry.deleted_at.is_(None)


def consumed_days(db: DbSession, engagement_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    if not engagement_ids:
        return {}
    per_day = get_settings().heures_par_jour
    rows = db.execute(
        select(TimeEntry.engagement_id, func.sum(TimeEntry.heures))
        .where(TimeEntry.engagement_id.in_(engagement_ids), _active())
        .group_by(TimeEntry.engagement_id)
    )
    return {eid: round(hours / per_day, 2) for eid, hours in rows}


def _out(e: TimeEntry) -> TimeEntryOut:
    return TimeEntryOut.model_validate(
        {
            **{k: getattr(e, k) for k in TimeEntryOut.model_fields if hasattr(e, k)},
            "user_nom": e.user.nom,
        }
    )


def _check_date(d: date) -> None:
    if d > date.today():
        raise HTTPException(422, "Le temps ne peut pas être saisi pour une date future")


@router.get("/{engagement_id}/time-entries", response_model=list[TimeEntryOut])
def list_entries(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[TimeEntryOut]:
    """Le chef de mission voit tous les temps ; chacun voit les siens."""
    engagement = get_engagement(db, engagement_id, user)
    query = select(TimeEntry).where(TimeEntry.engagement_id == engagement.id, _active())
    if not can_manage(engagement, user):
        query = query.where(TimeEntry.user_id == user.id)
    entries = db.scalars(query.order_by(TimeEntry.date.desc(), TimeEntry.created_at.desc()))
    return [_out(e) for e in entries]


@router.post("/{engagement_id}/time-entries", response_model=TimeEntryOut, status_code=201)
def add_entry(
    engagement_id: uuid.UUID, body: TimeEntryIn, user: CurrentUser, db: DbSession
) -> TimeEntryOut:
    engagement = get_engagement(db, engagement_id, user)
    require_member(engagement, user)
    ensure_open(engagement)
    _check_date(body.date)
    entry = TimeEntry(
        engagement_id=engagement.id,
        user_id=user.id,
        **body.model_dump(mode="json") | {"date": body.date},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _out(entry)


def _own_entry(
    db: DbSession, engagement_id: uuid.UUID, entry_id: uuid.UUID, user: User
) -> TimeEntry:
    engagement = get_engagement(db, engagement_id, user)
    ensure_open(engagement)
    entry = db.scalar(
        select(TimeEntry).where(
            TimeEntry.id == entry_id, TimeEntry.engagement_id == engagement.id, _active()
        )
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saisie introuvable")
    if entry.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chacun corrige ses propres saisies")
    return entry


@router.patch("/{engagement_id}/time-entries/{entry_id}", response_model=TimeEntryOut)
def update_entry(
    engagement_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: TimeEntryUpdate,
    user: CurrentUser,
    db: DbSession,
) -> TimeEntryOut:
    entry = _own_entry(db, engagement_id, entry_id, user)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("date"):
        _check_date(changes["date"])
    for key, value in changes.items():
        if value is not None or key == "commentaire":
            setattr(entry, key, value.value if key == "activite" else value)
    db.commit()
    return _out(entry)


@router.delete("/{engagement_id}/time-entries/{entry_id}", status_code=204)
def delete_entry(
    engagement_id: uuid.UUID, entry_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    entry = _own_entry(db, engagement_id, entry_id, user)
    entry.deleted_at = datetime.now(UTC)
    entry.deleted_by = user.id
    db.commit()


@router.get("/{engagement_id}/time-summary", response_model=TimeSummary)
def summary(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TimeSummary:
    engagement = get_engagement(db, engagement_id, user)
    per_day = get_settings().heures_par_jour
    base = select(func.sum(TimeEntry.heures)).where(
        TimeEntry.engagement_id == engagement.id, _active()
    )
    total = (db.scalar(base) or 0.0) / per_day
    by_user = db.execute(
        select(User.id, User.nom, func.sum(TimeEntry.heures))
        .join(User, User.id == TimeEntry.user_id)
        .where(TimeEntry.engagement_id == engagement.id, _active())
        .group_by(User.id, User.nom)
        .order_by(User.nom)
    )
    by_activity = db.execute(
        select(TimeEntry.activite, func.sum(TimeEntry.heures))
        .where(TimeEntry.engagement_id == engagement.id, _active())
        .group_by(TimeEntry.activite)
        .order_by(TimeEntry.activite)
    )
    budget = engagement.budget_jours
    return TimeSummary(
        budget_jours=budget,
        jours_consommes=round(total, 2),
        ecart_jours=round(budget - total, 2),
        taux_consommation=round(total / budget * 100, 1) if budget else 0.0,
        heures_par_jour=per_day,
        par_personne=[
            TimeLine(cle=str(uid), libelle=nom, jours=round(h / per_day, 2))
            for uid, nom, h in by_user
        ],
        par_activite=[
            TimeLine(cle=a, libelle=a, jours=round(h / per_day, 2)) for a, h in by_activity
        ],
    )
