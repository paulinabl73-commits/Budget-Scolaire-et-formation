"""Marques de révision paramétrables (AUD-16)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.models.user import User
from app.models.workpaper import Tickmark
from app.schemas_workpaper import TickmarkIn, TickmarkOut, TickmarkUpdate
from app.security.roles import Perm

router = APIRouter(prefix="/tickmarks", tags=["Marques de révision"])
Reader = Annotated[User, Depends(require(Perm.WORKPAPERS_READ))]
Settings = Annotated[User, Depends(require(Perm.SETTINGS_MANAGE, Perm.PLAN_MANAGE))]


@router.get("", response_model=list[TickmarkOut])
def list_tickmarks(_: Reader, db: DbSession) -> list[Tickmark]:
    return list(
        db.scalars(
            select(Tickmark)
            .where(Tickmark.deleted_at.is_(None))
            .order_by(Tickmark.ordre, Tickmark.symbole)
        )
    )


@router.post("", response_model=TickmarkOut, status_code=201)
def create_tickmark(body: TickmarkIn, _: Settings, db: DbSession) -> Tickmark:
    if db.scalar(select(Tickmark.id).where(Tickmark.symbole == body.symbole)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce symbole est déjà utilisé")
    tickmark = Tickmark(**body.model_dump(), actif=True)
    db.add(tickmark)
    db.commit()
    return tickmark


@router.patch("/{tickmark_id}", response_model=TickmarkOut)
def update_tickmark(
    tickmark_id: uuid.UUID, body: TickmarkUpdate, _: Settings, db: DbSession
) -> Tickmark:
    """Pas de suppression : une marque retirée se désactive et reste lisible dans les papiers."""
    tickmark = db.get(Tickmark, tickmark_id)
    if tickmark is None or tickmark.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Marque introuvable")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(tickmark, key, value)
    db.commit()
    return tickmark
