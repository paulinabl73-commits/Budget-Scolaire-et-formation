"""Critères paramétrables et évaluation des entités (AUD-02)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.api.universe import get_entity
from app.models.risk import RiskAssessment, RiskCriterion
from app.models.user import User
from app.risk_scoring import CriterionSpec, compute_score
from app.schemas_plan import (
    AssessmentIn,
    AssessmentOut,
    CriterionIn,
    CriterionOut,
    CriterionUpdate,
)
from app.security.roles import Perm

router = APIRouter(tags=["Évaluation des risques"])
Reader = Annotated[User, Depends(require(Perm.PLAN_READ))]
Manager = Annotated[User, Depends(require(Perm.PLAN_MANAGE))]
# Les critères sont un paramètre : Administrateur (paramètres) ou Directeur (méthodologie).
Settings = Annotated[User, Depends(require(Perm.SETTINGS_MANAGE, Perm.PLAN_MANAGE))]


def _criterion(db: DbSession, criterion_id: uuid.UUID) -> RiskCriterion:
    c = db.get(RiskCriterion, criterion_id)
    if c is None or c.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Critère introuvable")
    return c


@router.get("/risk/criteria", response_model=list[CriterionOut])
def list_criteria(_: Reader, db: DbSession) -> list[RiskCriterion]:
    return list(
        db.scalars(
            select(RiskCriterion)
            .where(RiskCriterion.deleted_at.is_(None))
            .order_by(RiskCriterion.ordre, RiskCriterion.code)
        )
    )


@router.post("/risk/criteria", response_model=CriterionOut, status_code=201)
def create_criterion(body: CriterionIn, _: Settings, db: DbSession) -> RiskCriterion:
    if db.scalar(select(RiskCriterion.id).where(RiskCriterion.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce code de critère existe déjà")
    c = RiskCriterion(**body.model_dump(mode="json"), actif=True)
    db.add(c)
    db.commit()
    return c


@router.patch("/risk/criteria/{criterion_id}", response_model=CriterionOut)
def update_criterion(
    criterion_id: uuid.UUID, body: CriterionUpdate, _: Settings, db: DbSession
) -> RiskCriterion:
    c = _criterion(db, criterion_id)
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        if value is not None:
            setattr(c, key, value)
    db.commit()
    return c


@router.get("/universe/entities/{entity_id}/assessments", response_model=list[AssessmentOut])
def list_assessments(entity_id: uuid.UUID, _: Reader, db: DbSession) -> list[RiskAssessment]:
    get_entity(db, entity_id)
    return list(
        db.scalars(
            select(RiskAssessment)
            .where(RiskAssessment.entity_id == entity_id)
            .order_by(RiskAssessment.date_evaluation.desc(), RiskAssessment.created_at.desc())
        )
    )


@router.post(
    "/universe/entities/{entity_id}/assessments", response_model=AssessmentOut, status_code=201
)
def assess(entity_id: uuid.UUID, body: AssessmentIn, _: Manager, db: DbSession) -> RiskAssessment:
    entity = get_entity(db, entity_id)
    criteria = [
        CriterionSpec(c.code, c.libelle, c.axe, c.mode, c.poids)
        for c in db.scalars(
            select(RiskCriterion)
            .where(RiskCriterion.actif.is_(True), RiskCriterion.deleted_at.is_(None))
            .order_by(RiskCriterion.ordre, RiskCriterion.code)
        )
    ]
    on = body.date_evaluation or date.today()
    try:
        result = compute_score(criteria, body.notes, entity.date_dernier_audit, on)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    assessment = RiskAssessment(
        entity_id=entity.id,
        date_evaluation=on,
        criteres=result.criteres,
        score=result.score,
        impact=result.impact,
        probabilite=result.probabilite,
        commentaire=body.commentaire,
    )
    db.add(assessment)
    # L'entité porte les résultats de son évaluation la plus récente.
    if entity.date_evaluation is None or on >= entity.date_evaluation:
        entity.score_risque = result.score
        entity.impact = result.impact
        entity.probabilite = result.probabilite
        entity.date_evaluation = on
    db.commit()
    return assessment
