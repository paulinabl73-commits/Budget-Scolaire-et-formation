"""Paramètres fiscaux par pays et par exercice (RCO-22)."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.cabinet.fiscal import catalog
from app.models.portfolio import FiscalParameter
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Portefeuille (Module 6)"])


class ParameterIn(BaseModel):
    pays: str = Field(min_length=2, max_length=40)
    code: str = Field(min_length=2, max_length=80)
    libelle: str | None = Field(default=None, max_length=300)
    valeur: Decimal = Field(max_digits=20, decimal_places=6)
    exercice: int | None = Field(default=None, ge=1990, le=2100)


def out(p: FiscalParameter) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "pays": p.pays,
        "code": p.code,
        "libelle": p.libelle,
        "valeur": format(p.valeur.normalize(), "f"),
        "unite": p.unite,
        "exercice": p.exercice,
    }


def _manager(user: Any) -> None:
    if not has_permission(user.role, Perm.PORTFOLIO_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux experts-comptables")


@router.get("/fiscal-parameters")
def list_parameters(user: CurrentUser, db: DbSession, pays: str | None = None) -> dict[str, Any]:
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    query = select(FiscalParameter).where(FiscalParameter.deleted_at.is_(None))
    if pays:
        query = query.where(FiscalParameter.pays == pays)
    rows = db.scalars(
        query.order_by(FiscalParameter.pays, FiscalParameter.code, FiscalParameter.exercice)
    )
    return {"catalogue": catalog(), "parametres": [out(p) for p in rows]}


@router.post("/fiscal-parameters", status_code=status.HTTP_201_CREATED)
def create_parameter(body: ParameterIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    _manager(user)
    known = {c["code"]: c for c in catalog()}
    if body.code not in known:
        raise HTTPException(422, "Paramètre inconnu du catalogue fiscal")
    duplicate = db.scalar(
        select(FiscalParameter).where(
            FiscalParameter.pays == body.pays,
            FiscalParameter.code == body.code,
            FiscalParameter.exercice.is_not_distinct_from(body.exercice),
            FiscalParameter.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Paramètre déjà défini pour ce pays et cet exercice"
        )
    p = FiscalParameter(
        pays=body.pays,
        code=body.code,
        libelle=body.libelle or known[body.code]["libelle"],
        valeur=body.valeur,
        unite=known[body.code]["unite"],
        exercice=body.exercice,
    )
    db.add(p)
    db.commit()
    return out(p)


@router.delete("/fiscal-parameters/{parameter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_parameter(parameter_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    _manager(user)
    p = db.get(FiscalParameter, parameter_id)
    if p is None or p.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paramètre introuvable")
    p.deleted_at, p.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()
