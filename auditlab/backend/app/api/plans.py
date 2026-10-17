"""Plan d'audit annuel (AUD-04)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require
from app.api.universe import get_entity
from app.models.plan import AuditPlan, PlanItem, PlanStatus
from app.models.user import User
from app.schemas_plan import (
    PlanIn,
    PlanItemIn,
    PlanItemOut,
    PlanItemUpdate,
    PlanOut,
    PlanSummary,
    PlanUpdate,
)
from app.security.roles import Perm

router = APIRouter(prefix="/plans", tags=["Plan annuel"])
Reader = Annotated[User, Depends(require(Perm.PLAN_READ))]
Manager = Annotated[User, Depends(require(Perm.PLAN_MANAGE))]


def get_plan(db: DbSession, plan_id: uuid.UUID) -> AuditPlan:
    plan = db.scalar(
        select(AuditPlan)
        .where(AuditPlan.id == plan_id, AuditPlan.deleted_at.is_(None))
        .options(selectinload(AuditPlan.items).selectinload(PlanItem.entity))
        .execution_options(populate_existing=True)
    )
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan introuvable")
    return plan


def editable_plan(db: DbSession, plan_id: uuid.UUID) -> AuditPlan:
    plan = get_plan(db, plan_id)
    if plan.statut != PlanStatus.BROUILLON:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ce plan n'est plus modifiable : créez une nouvelle version",
        )
    return plan


def summary(plan: AuditPlan) -> dict:
    return {
        **{k: getattr(plan, k) for k in PlanSummary.model_fields if hasattr(plan, k)},
        "nb_missions": len(plan.items),
        "total_jours": round(sum(i.budget_jours for i in plan.items), 2),
    }


def item_out(item: PlanItem) -> PlanItemOut:
    return PlanItemOut.model_validate(
        {
            **{k: getattr(item, k) for k in PlanItemOut.model_fields if hasattr(item, k)},
            "entity_nom": item.entity.nom,
            "score_risque": item.entity.score_risque,
        }
    )


def plan_out(plan: AuditPlan) -> PlanOut:
    return PlanOut.model_validate({**summary(plan), "items": [item_out(i) for i in plan.items]})


def _check_item(plan: AuditPlan, body: PlanItemIn | PlanItemUpdate, item: PlanItem | None) -> None:
    debut = body.periode_debut or (item.periode_debut if item else None)
    fin = body.periode_fin or (item.periode_fin if item else None)
    if debut and fin:
        if fin < debut:
            raise HTTPException(422, "La fin de la période précède son début")
        if debut.year != plan.annee or fin.year != plan.annee:
            raise HTTPException(422, f"La période doit être comprise dans l'année {plan.annee}")


@router.get("", response_model=list[PlanSummary])
def list_plans(_: Reader, db: DbSession, annee: int | None = None) -> list[dict]:
    query = (
        select(AuditPlan)
        .where(AuditPlan.deleted_at.is_(None))
        .options(selectinload(AuditPlan.items))
        .order_by(AuditPlan.annee.desc(), AuditPlan.version.desc())
    )
    if annee is not None:
        query = query.where(AuditPlan.annee == annee)
    return [summary(p) for p in db.scalars(query)]


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, _: Manager, db: DbSession) -> PlanOut:
    if db.scalar(select(AuditPlan.id).where(AuditPlan.annee == body.annee)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Un plan {body.annee} existe déjà : créez-en une nouvelle version",
        )
    plan = AuditPlan(
        annee=body.annee,
        version=1,
        statut=PlanStatus.BROUILLON.value,
        capacite_jours=body.capacite_jours,
        commentaire=body.commentaire,
    )
    db.add(plan)
    db.commit()
    return plan_out(get_plan(db, plan.id))


@router.get("/{plan_id}", response_model=PlanOut)
def read_plan(plan_id: uuid.UUID, _: Reader, db: DbSession) -> PlanOut:
    return plan_out(get_plan(db, plan_id))


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, body: PlanUpdate, _: Manager, db: DbSession) -> PlanOut:
    plan = editable_plan(db, plan_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)
    db.commit()
    return plan_out(get_plan(db, plan.id))


@router.post("/{plan_id}/items", response_model=PlanItemOut, status_code=201)
def add_item(plan_id: uuid.UUID, body: PlanItemIn, _: Manager, db: DbSession) -> PlanItemOut:
    plan = editable_plan(db, plan_id)
    entity = get_entity(db, body.entity_id)
    if any(i.entity_id == entity.id for i in plan.items):
        raise HTTPException(status.HTTP_409_CONFLICT, f"« {entity.nom} » figure déjà au plan")
    _check_item(plan, body, None)
    item = PlanItem(
        plan_id=plan.id,
        entity_id=entity.id,
        titre=body.titre or f"Audit {entity.nom}",
        budget_jours=body.budget_jours,
        periode_debut=body.periode_debut,
        periode_fin=body.periode_fin,
        justification=body.justification,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_out(item)


def _item(plan: AuditPlan, item_id: uuid.UUID) -> PlanItem:
    item = next((i for i in plan.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission introuvable dans ce plan")
    return item


@router.patch("/{plan_id}/items/{item_id}", response_model=PlanItemOut)
def update_item(
    plan_id: uuid.UUID, item_id: uuid.UUID, body: PlanItemUpdate, _: Manager, db: DbSession
) -> PlanItemOut:
    plan = editable_plan(db, plan_id)
    item = _item(plan, item_id)
    _check_item(plan, body, item)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key == "justification":
            setattr(item, key, value)
    db.commit()
    return item_out(item)


@router.delete("/{plan_id}/items/{item_id}", status_code=204)
def remove_item(plan_id: uuid.UUID, item_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    plan = editable_plan(db, plan_id)
    item = _item(plan, item_id)
    item.deleted_at = datetime.now(UTC)
    item.deleted_by = user.id
    db.commit()
