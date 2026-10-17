"""Bibliothèque de risques et de contrôles réutilisables entre missions (AUD-10)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require
from app.models.program import Control, Risk, RiskControl
from app.models.user import User
from app.schemas_mission import (
    ControlIn,
    ControlOut,
    ControlUpdate,
    LinkIn,
    RiskIn,
    RiskOut,
    RiskUpdate,
)
from app.security.roles import Perm

router = APIRouter(prefix="/library", tags=["Bibliothèque"])
Reader = Annotated[User, Depends(require(Perm.MISSIONS_READ_ALL, Perm.MISSIONS_READ_OWN))]
# La méthodologie est tenue par le Directeur et les chefs de mission.
Manager = Annotated[User, Depends(require(Perm.MISSIONS_MANAGE))]


def linked_controls(db: Session, risk_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Control]]:
    result: dict[uuid.UUID, list[Control]] = {rid: [] for rid in risk_ids}
    rows = db.execute(
        select(RiskControl.risk_id, Control)
        .join(Control, Control.id == RiskControl.control_id)
        .where(
            RiskControl.risk_id.in_(risk_ids),
            RiskControl.deleted_at.is_(None),
            Control.deleted_at.is_(None),
        )
        .order_by(Control.libelle)
    )
    for risk_id, control in rows:
        result[risk_id].append(control)
    return result


def risk_out(risk: Risk, controls: list[Control]) -> RiskOut:
    return RiskOut.model_validate(
        {
            **{k: getattr(risk, k) for k in RiskOut.model_fields if hasattr(risk, k)},
            "controles": [ControlOut.model_validate(c) for c in controls],
        }
    )


def set_links(db: Session, risk: Risk, control_ids: list[uuid.UUID]) -> None:
    current = {
        link.control_id: link
        for link in db.scalars(
            select(RiskControl).where(
                RiskControl.risk_id == risk.id, RiskControl.deleted_at.is_(None)
            )
        )
    }
    for control_id, link in current.items():
        if control_id not in control_ids:
            link.deleted_at = datetime.now(UTC)
    for control_id in control_ids:
        if control_id not in current:
            db.add(RiskControl(risk_id=risk.id, control_id=control_id))


def _library_risk(db: Session, risk_id: uuid.UUID) -> Risk:
    risk = db.scalar(
        select(Risk).where(
            Risk.id == risk_id, Risk.bibliotheque.is_(True), Risk.deleted_at.is_(None)
        )
    )
    if risk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Risque introuvable dans la bibliothèque")
    return risk


def _library_control(db: Session, control_id: uuid.UUID) -> Control:
    control = db.scalar(
        select(Control).where(
            Control.id == control_id, Control.bibliotheque.is_(True), Control.deleted_at.is_(None)
        )
    )
    if control is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrôle introuvable dans la bibliothèque")
    return control


@router.get("/risks", response_model=list[RiskOut])
def list_risks(_: Reader, db: DbSession, cycle: str | None = None) -> list[RiskOut]:
    query = select(Risk).where(Risk.bibliotheque.is_(True), Risk.deleted_at.is_(None))
    if cycle:
        query = query.where(Risk.cycle == cycle)
    risks = list(db.scalars(query.order_by(Risk.cycle, Risk.libelle)))
    links = linked_controls(db, [r.id for r in risks])
    return [risk_out(r, links[r.id]) for r in risks]


@router.post("/risks", response_model=RiskOut, status_code=201)
def create_risk(body: RiskIn, _: Manager, db: DbSession) -> RiskOut:
    risk = Risk(**body.model_dump(mode="json"), bibliotheque=True)
    db.add(risk)
    db.commit()
    return risk_out(risk, [])


@router.patch("/risks/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: uuid.UUID, body: RiskUpdate, _: Manager, db: DbSession) -> RiskOut:
    risk = _library_risk(db, risk_id)
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        if value is not None or key == "description":
            setattr(risk, key, value)
    db.commit()
    return risk_out(risk, linked_controls(db, [risk.id])[risk.id])


@router.put("/risks/{risk_id}/controls", response_model=RiskOut)
def link_controls(risk_id: uuid.UUID, body: LinkIn, _: Manager, db: DbSession) -> RiskOut:
    risk = _library_risk(db, risk_id)
    for control_id in body.control_ids:
        _library_control(db, control_id)
    set_links(db, risk, list(dict.fromkeys(body.control_ids)))
    db.commit()
    return risk_out(risk, linked_controls(db, [risk.id])[risk.id])


@router.delete("/risks/{risk_id}", status_code=204)
def delete_risk(risk_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    risk = _library_risk(db, risk_id)
    set_links(db, risk, [])
    risk.deleted_at = datetime.now(UTC)
    risk.deleted_by = user.id
    db.commit()


@router.get("/controls", response_model=list[ControlOut])
def list_controls(_: Reader, db: DbSession, cycle: str | None = None) -> list[Control]:
    query = select(Control).where(Control.bibliotheque.is_(True), Control.deleted_at.is_(None))
    if cycle:
        query = query.where(Control.cycle == cycle)
    return list(db.scalars(query.order_by(Control.cycle, Control.libelle)))


@router.post("/controls", response_model=ControlOut, status_code=201)
def create_control(body: ControlIn, _: Manager, db: DbSession) -> Control:
    control = Control(**body.model_dump(mode="json"), bibliotheque=True)
    db.add(control)
    db.commit()
    return control


@router.patch("/controls/{control_id}", response_model=ControlOut)
def update_control(
    control_id: uuid.UUID, body: ControlUpdate, _: Manager, db: DbSession
) -> Control:
    control = _library_control(db, control_id)
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        if value is not None or key == "description":
            setattr(control, key, value)
    db.commit()
    return control


@router.delete("/controls/{control_id}", status_code=204)
def delete_control(control_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    control = _library_control(db, control_id)
    now = datetime.now(UTC)
    for link in db.scalars(
        select(RiskControl).where(
            RiskControl.control_id == control.id, RiskControl.deleted_at.is_(None)
        )
    ):
        link.deleted_at = now
    control.deleted_at = now
    control.deleted_by = user.id
    db.commit()
