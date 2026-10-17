"""Plans d'action des constats (CON-05) et leur vérification par l'audit (CON-07).

Le suivi se poursuit après la clôture de la mission : les écritures sur les plans ne
passent pas par ensure_open, seulement par les droits sur la mission.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.findings import can_write, get_finding
from app.api.mission_access import can_manage, get_engagement
from app.models.engagement import Engagement
from app.models.finding import (
    CLOSED_PLAN_STATUSES,
    ActionPlan,
    ActionPlanStatus,
    Finding,
    FindingStatus,
)
from app.models.user import User
from app.schemas_finding import PlanIn, PlanOut, PlanStatusIn, PlanUpdate
from app.security.roles import Perm, Role, has_permission

router = APIRouter(tags=["Plans d'action"])

S = ActionPlanStatus


def is_owner(plan: ActionPlan, finding: Finding, user: User) -> bool:
    """Responsable du plan ou audité destinataire du constat."""
    return user.id in (plan.responsable_id, finding.audite_id)


def transitions(
    plan: ActionPlan, finding: Finding, engagement: Engagement, user: User
) -> list[str]:
    """Statuts accessibles à l'utilisateur depuis le statut courant du plan."""
    current = plan.statut
    if current in CLOSED_PLAN_STATUSES:
        return []
    auditor = can_write(engagement, user) or can_manage(engagement, user)
    owner = is_owner(plan, finding, user)
    allowed: list[str] = []
    if auditor or owner:
        allowed += {
            S.A_LANCER.value: [S.EN_COURS.value, S.REALISE.value],
            S.EN_COURS.value: [S.REALISE.value],
            S.REALISE.value: [S.EN_COURS.value] if owner else [],
        }[current]
    if auditor and current == S.REALISE.value:
        allowed.append(S.VERIFIE.value)  # CON-07 : vérification par l'audit
    if can_manage(engagement, user):
        allowed.append(S.RISQUE_ACCEPTE.value)  # décision tracée, justification obligatoire
    return list(dict.fromkeys(allowed))


def plan_out(db: Session, plan: ActionPlan, user: User | None = None) -> PlanOut:
    out = PlanOut.model_validate(plan)
    finding = db.get(Finding, plan.finding_id)
    out.responsable = db.get(User, plan.responsable_id).nom if plan.responsable_id else None
    out.responsable = out.responsable or plan.responsable_nom
    out.en_retard = plan.statut not in CLOSED_PLAN_STATUSES + (S.REALISE.value,) and (
        plan.echeance < dt.date.today()
    )
    out.constat_reference, out.constat_titre = finding.reference, finding.titre
    out.mission_id = finding.engagement_id
    if user is not None:
        engagement = db.get(Engagement, finding.engagement_id)
        out.transitions = transitions(plan, finding, engagement, user)
    return out


def _check_responsable(db: Session, data: dict) -> None:
    if data.get("responsable_id"):
        person = db.get(User, data["responsable_id"])
        if person is None or not person.actif:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Responsable inconnu")


def get_plan(db: Session, plan_id: uuid.UUID) -> ActionPlan:
    plan = db.scalar(
        select(ActionPlan).where(ActionPlan.id == plan_id, ActionPlan.deleted_at.is_(None))
    )
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan d'action introuvable")
    return plan


def plan_context(db: Session, plan: ActionPlan, user: User) -> tuple[Finding, Engagement]:
    """Accès au plan : membres de la mission (et Directeur), ou responsable / audité."""
    finding = db.get(Finding, plan.finding_id)
    if user.role == Role.AUDITE.value:
        if not is_owner(plan, finding, user):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan d'action introuvable")
        return finding, db.get(Engagement, finding.engagement_id)
    finding, engagement = get_finding(db, finding.id, user)
    return finding, engagement


def require_auditor(engagement: Engagement, user: User) -> None:
    if not (can_write(engagement, user) or can_manage(engagement, user)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux auditeurs et au chef de la mission"
        )


@router.get("/findings/{finding_id}/action-plans", response_model=list[PlanOut])
def list_plans(finding_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[PlanOut]:
    finding, _ = get_finding(db, finding_id, user)
    plans = db.scalars(
        select(ActionPlan)
        .where(ActionPlan.finding_id == finding.id, ActionPlan.deleted_at.is_(None))
        .order_by(ActionPlan.echeance, ActionPlan.created_at)
    )
    return [plan_out(db, p, user) for p in plans]


@router.post(
    "/findings/{finding_id}/action-plans",
    response_model=PlanOut,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(finding_id: uuid.UUID, body: PlanIn, user: CurrentUser, db: DbSession) -> PlanOut:
    finding, engagement = get_finding(db, finding_id, user)
    require_auditor(engagement, user)
    data = body.model_dump()
    _check_responsable(db, data)
    plan = ActionPlan(finding_id=finding.id, **data)
    db.add(plan)
    db.commit()
    return plan_out(db, plan, user)


@router.patch("/action-plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, body: PlanUpdate, user: CurrentUser, db: DbSession) -> PlanOut:
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    require_auditor(engagement, user)
    if plan.statut in CLOSED_PLAN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan clos : modification impossible")
    data = body.model_dump(exclude_unset=True)
    if "echeance" in data and finding.statut == FindingStatus.VALIDE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Constat validé : l'échéance ne change que par une demande de report (CON-08)",
        )
    _check_responsable(db, data)
    for key, value in data.items():
        setattr(plan, key, value)
    db.commit()
    return plan_out(db, plan, user)


@router.post("/action-plans/{plan_id}/status", response_model=PlanOut)
def change_status(
    plan_id: uuid.UUID, body: PlanStatusIn, user: CurrentUser, db: DbSession
) -> PlanOut:
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    if body.statut not in transitions(plan, finding, engagement, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Changement de statut non permis")
    if body.statut == S.RISQUE_ACCEPTE.value and not (body.commentaire or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Justification obligatoire pour accepter le risque",
        )
    plan.statut = body.statut
    if body.commentaire:
        plan.commentaire = body.commentaire
    if body.statut == S.VERIFIE.value:
        plan.verifie_le, plan.verifie_par = dt.datetime.now(dt.UTC), user.id
    db.commit()
    return plan_out(db, plan, user)


@router.get("/engagements/{engagement_id}/action-plans", response_model=list[PlanOut])
def mission_plans(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[PlanOut]:
    """Suivi des plans d'action de la mission (tous constats confondus)."""
    engagement = get_engagement(db, engagement_id, user)
    if not has_permission(user.role, Perm.FINDINGS_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    plans = db.scalars(
        select(ActionPlan)
        .join(Finding, Finding.id == ActionPlan.finding_id)
        .where(
            Finding.engagement_id == engagement.id,
            Finding.deleted_at.is_(None),
            ActionPlan.deleted_at.is_(None),
        )
        .order_by(ActionPlan.echeance)
    )
    return [plan_out(db, p, user) for p in plans]
