import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.audit.chain import verify_chain
from app.audit.listeners import record_event
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas import AuditLogOut, AuditLogPage, ChainReportOut
from app.security.roles import Perm

router = APIRouter(prefix="/audit-log", tags=["Journal d'audit"])
Reader = Annotated[User, Depends(require(Perm.AUDIT_LOG_READ))]


@router.get("", response_model=AuditLogPage)
def list_entries(
    _: Reader,
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    user_id: uuid.UUID | None = None,
    depuis: datetime | None = None,
    jusqu_a: datetime | None = None,
) -> AuditLogPage:
    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if object_type:
        filters.append(AuditLog.object_type == object_type)
    if object_id:
        filters.append(AuditLog.object_id == object_id)
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if depuis:
        filters.append(AuditLog.horodatage >= depuis)
    if jusqu_a:
        filters.append(AuditLog.horodatage <= jusqu_a)

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    rows = db.execute(
        select(AuditLog, User.nom)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*filters)
        .order_by(AuditLog.seq.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    items = [
        AuditLogOut.model_validate(entry).model_copy(update={"user_nom": nom})
        for entry, nom in rows
    ]
    return AuditLogPage(total=total, items=items)


@router.get("/verify", response_model=ChainReportOut)
def verify(_: Reader, db: DbSession) -> ChainReportOut:
    report = verify_chain(db)
    record_event(
        db,
        "audit_chain_verified",
        object_type="AuditLog",
        details={"ok": report.ok, "entrees": report.entries, "rupture": report.first_broken_seq},
    )
    db.commit()
    return ChainReportOut(**report.__dict__)
