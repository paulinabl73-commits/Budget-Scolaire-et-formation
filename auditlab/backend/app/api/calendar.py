"""Calendrier fiscal et social paramétrable par pays (RCO-03)."""

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.portfolio import get_client, require_client_manager
from app.cabinet.calendar import client_deadlines
from app.models.portfolio import CalendarRule, ClientDeadline
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Portefeuille (Module 6)"])
REGIMES = Literal["reel_normal", "reel_simplifie", "entreprenant", "exonere", "autre"]


class RuleIn(BaseModel):
    pays: str = Field(min_length=2, max_length=40)
    code: str = Field(min_length=2, max_length=40)
    libelle: str = Field(min_length=2, max_length=300)
    nature: Literal["fiscal", "social", "juridique"]
    periodicite: Literal["mensuelle", "trimestrielle", "annuelle", "cloture"]
    jour: int | None = Field(default=None, ge=1, le=31)
    mois: int | None = Field(default=None, ge=1, le=12)
    decalage_mois: int | None = Field(default=None, ge=0, le=24)
    regimes: list[REGIMES] = []
    actif: bool = True

    @model_validator(mode="after")
    def _shape(self) -> "RuleIn":
        if self.periodicite in ("mensuelle", "trimestrielle", "annuelle") and self.jour is None:
            raise ValueError("Jour de l'échéance obligatoire")
        if self.periodicite == "annuelle" and self.mois is None:
            raise ValueError("Mois de l'échéance obligatoire")
        if self.periodicite == "cloture" and self.decalage_mois is None:
            raise ValueError("Nombre de mois après la clôture obligatoire")
        return self


class DoneIn(BaseModel):
    fait: bool
    date: dt.date | None = None


def rule_out(r: CalendarRule) -> dict[str, Any]:
    return {
        "id": str(r.id),
        **{
            k: getattr(r, k)
            for k in (
                "pays",
                "code",
                "libelle",
                "nature",
                "periodicite",
                "jour",
                "mois",
                "decalage_mois",
                "regimes",
                "actif",
            )
        },  # fmt: skip
    }


def _require_manager(user: Any) -> None:
    if not has_permission(user.role, Perm.PORTFOLIO_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux experts-comptables")


@router.get("/calendar-rules")
def list_rules(user: CurrentUser, db: DbSession, pays: str | None = None) -> list[dict[str, Any]]:
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    query = select(CalendarRule).where(CalendarRule.deleted_at.is_(None))
    if pays:
        query = query.where(CalendarRule.pays == pays)
    return [rule_out(r) for r in db.scalars(query.order_by(CalendarRule.pays, CalendarRule.code))]


@router.post("/calendar-rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    _require_manager(user)
    rule = CalendarRule(**body.model_dump())
    db.add(rule)
    db.commit()
    return rule_out(rule)


@router.put("/calendar-rules/{rule_id}")
def update_rule(
    rule_id: uuid.UUID, body: RuleIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    _require_manager(user)
    rule = db.get(CalendarRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Échéance introuvable")
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    db.commit()
    return rule_out(rule)


@router.delete("/calendar-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    _require_manager(user)
    rule = db.get(CalendarRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Échéance introuvable")
    rule.deleted_at, rule.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.get("/clients/{client_id}/deadlines")
def read_deadlines(
    client_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    du: dt.date | None = None,
    au: dt.date | None = None,
) -> list[dict[str, Any]]:
    client = get_client(db, client_id, user)
    today = dt.date.today()
    return client_deadlines(
        db, client, du or today - dt.timedelta(days=90), au or today + dt.timedelta(days=180)
    )


@router.put("/clients/{client_id}/deadlines/{rule_id}/{echeance}")
def mark_done(
    client_id: uuid.UUID,
    rule_id: uuid.UUID,
    echeance: dt.date,
    body: DoneIn,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    """Échéance faite (déclaration déposée) ou rouverte ; collaborateur ou expert du dossier."""
    client = get_client(db, client_id, user)
    if not has_permission(user.role, Perm.REVISION_WORK):
        require_client_manager(client, user)
    rule = db.get(CalendarRule, rule_id)
    if rule is None or rule.deleted_at is not None or rule.pays != client.pays:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Échéance introuvable")
    known = client_deadlines(db, client, echeance, echeance)
    if not any(d["rule_id"] == str(rule_id) for d in known):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pas d'échéance de cette règle à cette date")
    row = db.scalar(
        select(ClientDeadline).where(
            ClientDeadline.client_id == client.id,
            ClientDeadline.rule_id == rule_id,
            ClientDeadline.echeance == echeance,
            ClientDeadline.deleted_at.is_(None),
        )
    )
    if row is None:
        row = ClientDeadline(client_id=client.id, rule_id=rule_id, echeance=echeance, alertes=[])
        db.add(row)
    row.fait_le = (body.date or dt.date.today()) if body.fait else None
    db.commit()
    return next(
        d for d in client_deadlines(db, client, echeance, echeance) if d["rule_id"] == str(rule_id)
    )
