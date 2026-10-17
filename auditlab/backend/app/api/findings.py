"""Constats (Module 3) : fiche en cinq volets, criticité, rattachements (CON-01, CON-02)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import ensure_open, get_engagement, mission_role
from app.models.engagement import Engagement, MissionRole
from app.models.finding import CRITICALITY_ORDER, Finding, FindingStatus
from app.models.program import Control, Risk
from app.models.user import User
from app.models.workpaper import Workpaper
from app.schemas_finding import FindingIn, FindingOut, FindingUpdate
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Constats"])

WRITER_ROLES = (MissionRole.CHEF, MissionRole.AUDITEUR)
EDITABLE = (FindingStatus.BROUILLON.value, FindingStatus.REPONDU.value)


def can_write(engagement: Engagement, user: User) -> bool:
    return mission_role(engagement, user) in WRITER_ROLES and has_permission(
        user.role, Perm.FINDINGS_WRITE
    )


def require_writer(engagement: Engagement, user: User) -> None:
    ensure_open(engagement)
    if not can_write(engagement, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux auditeurs et au chef de la mission"
        )


def get_finding(db: Session, finding_id: uuid.UUID, user: User) -> tuple[Finding, Engagement]:
    finding = db.scalar(
        select(Finding).where(Finding.id == finding_id, Finding.deleted_at.is_(None))
    )
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Constat introuvable")
    engagement = get_engagement(db, finding.engagement_id, user)
    if not has_permission(user.role, Perm.FINDINGS_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    return finding, engagement


def _next_reference(db: Session, engagement: Engagement) -> str:
    count = (
        db.scalar(
            select(func.count()).select_from(Finding).where(Finding.engagement_id == engagement.id)
        )
        or 0
    )
    return f"C-{count + 1:02d}"


def _check_links(db: Session, engagement: Engagement, data: dict) -> None:
    """CON-02 : risque, contrôle et papiers de travail de la même mission."""
    checks = (("risk_id", Risk, "Risque"), ("control_id", Control, "Contrôle"))
    for key, model, label in checks:
        if data.get(key):
            obj = db.get(model, data[key])
            if obj is None or obj.engagement_id != engagement.id or obj.deleted_at:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label} inconnu dans cette mission"
                )
    if data.get("workpaper_ids") is not None:
        ids = list(dict.fromkeys(data["workpaper_ids"]))
        found = db.scalars(
            select(Workpaper.id).where(
                Workpaper.id.in_(ids),
                Workpaper.engagement_id == engagement.id,
                Workpaper.deleted_at.is_(None),
            )
        ).all()
        if len(found) != len(ids):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Papier de travail inconnu dans cette mission",
            )
        data["workpaper_ids"] = [str(i) for i in ids]


def finding_out(db: Session, f: Finding, engagement: Engagement, user: User) -> FindingOut:
    out = FindingOut.model_validate(f)
    if f.risk_id:
        out.risque = db.get(Risk, f.risk_id).libelle
    if f.control_id:
        out.controle = db.get(Control, f.control_id).libelle
    if f.workpaper_ids:
        papers = db.scalars(
            select(Workpaper).where(Workpaper.id.in_([uuid.UUID(i) for i in f.workpaper_ids]))
        )
        out.papiers = [
            {"id": str(w.id), "reference": w.reference, "titre": w.titre} for w in papers
        ]
    if f.audite_id:
        out.audite_nom = db.get(User, f.audite_id).nom
    out.peut_modifier = (
        f.statut in EDITABLE and engagement.statut != "cloturee" and can_write(engagement, user)
    )
    return out


@router.get("/engagements/{engagement_id}/findings", response_model=list[FindingOut])
def list_findings(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[FindingOut]:
    engagement = get_engagement(db, engagement_id, user)
    if not has_permission(user.role, Perm.FINDINGS_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    rows = db.scalars(
        select(Finding).where(Finding.engagement_id == engagement.id, Finding.deleted_at.is_(None))
    ).all()
    # Ordre du rapport : criticité décroissante, puis référence.
    rows = sorted(rows, key=lambda f: (-CRITICALITY_ORDER.index(f.criticite), f.reference))
    return [finding_out(db, f, engagement, user) for f in rows]


@router.post(
    "/engagements/{engagement_id}/findings",
    response_model=FindingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_finding(
    engagement_id: uuid.UUID, body: FindingIn, user: CurrentUser, db: DbSession
) -> FindingOut:
    engagement = get_engagement(db, engagement_id, user)
    require_writer(engagement, user)
    data = body.model_dump()
    _check_links(db, engagement, data)
    finding = Finding(
        engagement_id=engagement.id, reference=_next_reference(db, engagement), **data
    )
    db.add(finding)
    db.commit()
    return finding_out(db, finding, engagement, user)


@router.get("/findings/{finding_id}", response_model=FindingOut)
def read_finding(finding_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FindingOut:
    finding, engagement = get_finding(db, finding_id, user)
    return finding_out(db, finding, engagement, user)


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: uuid.UUID, body: FindingUpdate, user: CurrentUser, db: DbSession
) -> FindingOut:
    finding, engagement = get_finding(db, finding_id, user)
    require_writer(engagement, user)
    if finding.statut not in EDITABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Constat en phase contradictoire ou validé : modification impossible",
        )
    data = body.model_dump(exclude_unset=True)
    _check_links(db, engagement, data)
    for key, value in data.items():
        setattr(finding, key, value)
    db.commit()
    return finding_out(db, finding, engagement, user)


@router.delete("/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_finding(finding_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    finding, engagement = get_finding(db, finding_id, user)
    require_writer(engagement, user)
    if finding.statut != FindingStatus.BROUILLON.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un constat en brouillon se supprime")
    finding.deleted_at, finding.deleted_by = datetime.now(UTC), user.id
    db.commit()
