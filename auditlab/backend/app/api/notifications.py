"""Notifications de l'utilisateur connecté."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.notification import Notification

router = APIRouter(prefix="/me/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    titre: str
    message: str
    lien: str | None
    lue_le: datetime | None
    created_at: datetime | None


class NotificationPage(BaseModel):
    non_lues: int
    items: list[NotificationOut]


@router.get("", response_model=NotificationPage)
def my_notifications(user: CurrentUser, db: DbSession, limit: int = 30) -> NotificationPage:
    base = select(Notification).where(
        Notification.user_id == user.id, Notification.deleted_at.is_(None)
    )
    unread = (
        db.scalar(
            select(func.count()).select_from(base.where(Notification.lue_le.is_(None)).subquery())
        )
        or 0
    )
    items = db.scalars(base.order_by(Notification.created_at.desc()).limit(min(limit, 200)))
    return NotificationPage(non_lues=unread, items=list(items))


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification introuvable")
    n.lue_le = n.lue_le or datetime.now(UTC)
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(user: CurrentUser, db: DbSession) -> None:
    now = datetime.now(UTC)
    for n in db.scalars(
        select(Notification).where(Notification.user_id == user.id, Notification.lue_le.is_(None))
    ):
        n.lue_le = now
    db.commit()
