"""Macros (DAT-25) : création depuis l'historique d'une table, liste et exécution."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.analytics.macros import MacroError, build_macro, plan_run
from app.api.datasets import dataset_out, get_dataset, require_analyst
from app.api.deps import CurrentUser, DbSession
from app.models.data import Macro
from app.schemas_data import DatasetOut
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Macros"])


class MacroIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    description: str | None = None


class MacroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    description: str | None
    entrees: list[dict[str, Any]]
    etapes: list[dict[str, Any]]
    origine_dataset_id: uuid.UUID | None
    created_at: datetime | None = None


class RunIn(BaseModel):
    entrees: list[uuid.UUID] = Field(min_length=1, max_length=10)
    suffixe: str = Field(default="", max_length=60)


def _get(db: DbSession, macro_id: uuid.UUID) -> Macro:
    macro = db.scalar(select(Macro).where(Macro.id == macro_id, Macro.deleted_at.is_(None)))
    if macro is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Macro introuvable")
    return macro


@router.post(
    "/datasets/{dataset_id}/macro", response_model=MacroOut, status_code=status.HTTP_201_CREATED
)
def create_macro(dataset_id: uuid.UUID, body: MacroIn, user: CurrentUser, db: DbSession) -> Macro:
    ds, engagement = get_dataset(db, dataset_id, user)
    if not has_permission(user.role, Perm.DATA_ANALYZE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    try:
        macro = build_macro(db, ds, body.nom, body.description)
    except MacroError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.add(macro)
    db.commit()
    return macro


@router.get("/macros", response_model=list[MacroOut])
def list_macros(user: CurrentUser, db: DbSession) -> list[Macro]:
    if not has_permission(user.role, Perm.DATA_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    return list(db.scalars(select(Macro).where(Macro.deleted_at.is_(None)).order_by(Macro.nom)))


@router.post(
    "/macros/{macro_id}/run",
    response_model=list[DatasetOut],
    status_code=status.HTTP_202_ACCEPTED,
)
def run(macro_id: uuid.UUID, body: RunIn, user: CurrentUser, db: DbSession) -> list[DatasetOut]:
    """Rejoue la macro sur de nouvelles tables de même structure."""
    from app.analytics.jobs import run_macro

    macro = _get(db, macro_id)
    inputs = []
    for dataset_id in body.entrees:
        ds, engagement = get_dataset(db, dataset_id, user)
        require_analyst(engagement, user)
        inputs.append(ds)
    try:
        created = plan_run(db, macro, inputs, body.suffixe)
    except MacroError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    run_macro.delay([str(d.id) for d in created])
    for d in created:
        db.refresh(d)
    return [dataset_out(d) for d in created]
