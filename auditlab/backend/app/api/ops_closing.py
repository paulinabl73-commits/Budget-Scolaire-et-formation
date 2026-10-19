"""Écritures de clôture d'un organisme de prévoyance sociale (RCO-16) : cotisations à
recevoir, prestations à payer et provisions techniques par branche.

Provision technique requise d'une branche = minimum réglementaire en mois de prestations
(paramètre reserve_technique_mois, CIP-09) × prestations de l'exercice / 12 (indicateurs du
CIP-07, poste PRE) ; la dotation ou la reprise porte la réserve (poste RTE) à ce niveau. Les
comptes sont saisis : le plan CIPRES en vigueur est propre à chaque organisme."""

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.api.ops_controls import cipres
from app.cabinet.entries import propose
from app.models.portfolio import Client, OpsClosingItem
from app.models.revision import AuditFile
from app.revision.balances import clean_account
from app.revision.controls import plan_roots
from app.revision.currency import decimals, quantum
from app.revision.ops import Context
from app.revision.ops_indicators import reserves

router = APIRouter(tags=["Portefeuille (Module 6)"])
ORIGIN = "RCO-16"
NATURES = ("cotisations_a_recevoir", "prestations_a_payer", "provision_technique")


class ItemIn(BaseModel):
    nature: Literal[NATURES]  # type: ignore[valid-type]
    branche: str = Field(min_length=1, max_length=20)
    libelle: str = Field(min_length=2, max_length=300)
    compte_debit: str = Field(min_length=2, max_length=30)
    compte_credit: str = Field(min_length=2, max_length=30)
    compte_reprise: str | None = Field(default=None, max_length=30)
    montant: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)

    @model_validator(mode="after")
    def _shape(self) -> "ItemIn":
        if self.nature == "provision_technique":
            if not self.compte_reprise:
                raise ValueError("Compte de reprise obligatoire pour une provision technique")
        elif self.montant is None:
            raise ValueError("Montant obligatoire")
        return self


def build(db: Session, file: AuditFile) -> dict[str, Any]:
    fw = cipres(db, file)
    ctx = Context(db, file, fw)
    q = quantum(decimals(db, file.devise))
    technical = reserves(db, file, ctx)
    required = {}
    for b in technical["branches"]:
        if b["minimum_mois"] is None:
            continue
        need = (Decimal(b["minimum_mois"]) * Decimal(b["prestations"]) / 12).quantize(
            q, ROUND_HALF_UP
        )
        required[b["code"]] = {"requise": need, "constituee": Decimal(b["reserves"])}
    rows = db.scalars(
        select(OpsClosingItem)
        .where(OpsClosingItem.audit_file_id == file.id, OpsClosingItem.deleted_at.is_(None))
        .order_by(OpsClosingItem.nature, OpsClosingItem.branche)
    )
    items = []
    for r in rows:
        item = {
            "id": str(r.id),
            "nature": r.nature,
            "branche": r.branche,
            "libelle": r.libelle,
            "compte_debit": r.compte_debit,
            "compte_credit": r.compte_credit,
            "compte_reprise": r.compte_reprise,
            "montant": str(r.montant) if r.montant else None,
        }
        if r.nature == "provision_technique":
            reserve = required.get(r.branche)
            item["montant"] = str(reserve["requise"] - reserve["constituee"]) if reserve else None
        items.append(item)
    return {
        "elements": items,
        "provisions_techniques": [
            {
                "branche": k,
                "requise": str(v["requise"]),
                "constituee": str(v["constituee"]),
                "ecart": str(v["requise"] - v["constituee"]),
            }
            for k, v in sorted(required.items())
        ],
        "postes_manquants": technical["postes_manquants"],
        "parametres_manquants": ctx.missing,
        "branches": [b["code"] for b in fw.branches],
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


@router.get("/audit-files/{file_id}/ops-closing")
def read_items(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return build(db, file)


@router.post("/audit-files/{file_id}/ops-closing", status_code=status.HTTP_201_CREATED)
def add_item(file_id: uuid.UUID, body: ItemIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    fw = cipres(db, file)
    if body.branche not in {b["code"] for b in fw.branches}:
        raise HTTPException(422, "Branche inconnue du référentiel")
    roots = plan_roots(db, file.framework_id)
    data = body.model_dump()
    for key in ("compte_debit", "compte_credit", "compte_reprise"):
        if data[key]:
            data[key] = clean_account(data[key])
            if not any(data[key].startswith(r) for r in roots):
                raise HTTPException(422, f"Compte {data[key]} hors plan")
    if body.nature == "provision_technique":
        data["montant"] = None
    db.add(OpsClosingItem(client_id=client.id, audit_file_id=file.id, **data))
    db.commit()
    return build(db, file)


@router.delete("/audit-files/{file_id}/ops-closing/{item_id}", status_code=204)
def delete_item(file_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    file, _ = _context(db, file_id, user, True)
    row = db.get(OpsClosingItem, item_id)
    if row is None or row.deleted_at is not None or row.audit_file_id != file.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Élément introuvable")
    row.deleted_at, row.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/audit-files/{file_id}/ops-closing/entry", status_code=status.HTTP_201_CREATED)
def ops_entry(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, True)
    data = build(db, file)
    lines = []
    for e in data["elements"]:
        if e["montant"] is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Provision technique {e['branche']} non calculable, paramètres ou postes "
                "manquants : " + ", ".join(data["parametres_manquants"] + data["postes_manquants"]),
            )
        amount = Decimal(e["montant"])
        label = f"{e['branche']} : {e['libelle']}"
        if amount > 0:
            lines += [
                {"compte": e["compte_debit"], "libelle": label, "debit": amount},
                {"compte": e["compte_credit"], "libelle": label, "credit": amount},
            ]
        elif amount < 0:  # reprise de provision technique excédentaire
            lines += [
                {"compte": e["compte_credit"], "libelle": label, "debit": -amount},
                {"compte": e["compte_reprise"], "libelle": label, "credit": -amount},
            ]
    return propose(
        db,
        file,
        user,
        ORIGIN,
        f"Écritures de clôture de l'organisme {file.exercice}",
        "Cotisations à recevoir, prestations à payer et provisions techniques par branche "
        f"(RCO-16) : {len(data['elements'])} élément(s).",
        lines,
    )
