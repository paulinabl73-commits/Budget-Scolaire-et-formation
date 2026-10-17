"""Portail audité (CON-09) : l'audité ne voit que ses constats et ses plans d'action.

Un constat est « à lui » s'il en est le destinataire, ou s'il est responsable d'un de ses
plans. Les constats en brouillon ne sont jamais visibles. Aucune autre donnée de la mission
(papiers, preuves internes, données analysées) n'est exposée.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.action_plans import plan_out
from app.api.contradictory import respond_to
from app.api.deps import CurrentUser, DbSession
from app.models.engagement import Engagement
from app.models.finding import CLOSED_PLAN_STATUSES, ActionPlan, Finding, FindingStatus
from app.models.user import User
from app.schemas_finding import ResponseIn
from app.security.roles import Perm, has_permission

router = APIRouter(prefix="/portal", tags=["Portail audité"])

PUBLIC_FIELDS = (
    "id", "reference", "titre", "critere", "constat", "cause", "consequence", "recommandation",
    "criticite", "statut", "date_limite_reponse", "reponse_position", "reponse_commentaire",
    "envoye_le", "repondu_le", "valide_le",
)  # fmt: skip


def require_portal(user: User) -> None:
    if not has_permission(user.role, Perm.FINDINGS_RESPOND):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Portail réservé aux audités")


def my_findings_query(user: User):  # noqa: ANN201
    plans = select(ActionPlan.finding_id).where(
        ActionPlan.responsable_id == user.id, ActionPlan.deleted_at.is_(None)
    )
    return select(Finding).where(
        Finding.deleted_at.is_(None),
        Finding.statut != FindingStatus.BROUILLON.value,
        or_(Finding.audite_id == user.id, Finding.id.in_(plans)),
    )


def portal_finding(db: Session, f: Finding, user: User, with_plans: bool) -> dict[str, Any]:
    out: dict[str, Any] = {k: getattr(f, k) for k in PUBLIC_FIELDS}
    engagement = db.get(Engagement, f.engagement_id)
    out["mission"] = {"reference": engagement.reference, "titre": engagement.titre}
    out["peut_repondre"] = f.statut == FindingStatus.ENVOYE.value and f.audite_id == user.id
    plans = db.scalars(
        select(ActionPlan)
        .where(ActionPlan.finding_id == f.id, ActionPlan.deleted_at.is_(None))
        .order_by(ActionPlan.echeance)
    ).all()
    out["plans_ouverts"] = sum(1 for p in plans if p.statut not in CLOSED_PLAN_STATUSES)
    out["plans_en_retard"] = sum(1 for p in plans if plan_out(db, p).en_retard)
    if with_plans:
        out["plans"] = [plan_out(db, p, user).model_dump(mode="json") for p in plans]
    return out


@router.get("/findings")
def my_findings(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    require_portal(user)
    rows = db.scalars(my_findings_query(user).order_by(Finding.envoye_le.desc())).all()
    return [portal_finding(db, f, user, with_plans=False) for f in rows]


def get_my_finding(db: Session, finding_id: uuid.UUID, user: User) -> Finding:
    require_portal(user)
    finding = db.scalar(my_findings_query(user).where(Finding.id == finding_id))
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Constat introuvable")
    return finding


@router.get("/findings/{finding_id}")
def my_finding(finding_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return portal_finding(db, get_my_finding(db, finding_id, user), user, with_plans=True)


@router.post("/findings/{finding_id}/response")
def answer(
    finding_id: uuid.UUID, body: ResponseIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    finding = get_my_finding(db, finding_id, user)
    if finding.audite_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul le destinataire répond au constat")
    respond_to(db, finding, body, user)
    db.commit()
    return portal_finding(db, finding, user, with_plans=True)
