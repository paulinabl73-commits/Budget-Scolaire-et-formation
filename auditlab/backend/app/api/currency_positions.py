"""Opérations en devises d'une clôture (RCO-15) : écarts de conversion au cours de clôture et
provision pour perte de change.

Écart = montant en devise × cours de clôture − valeur comptable. Pour une créance, une
baisse est une perte latente (écart de conversion actif) ; pour une dette, une hausse. Les
gains latents vont en écart de conversion passif. La provision couvre les pertes latentes,
sans compensation avec les gains."""

import datetime as dt
import json
import uuid
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.cabinet.entries import propose
from app.models.portfolio import Client, CurrencyPosition
from app.models.revision import AccountingFramework, AuditFile
from app.revision.balances import clean_account
from app.revision.controls import plan_roots
from app.revision.currency import decimals, find_rate, quantum
from app.revision.mapping import assignments

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
ORIGIN = "RCO-15"


class PositionIn(BaseModel):
    compte: str = Field(min_length=2, max_length=30)
    libelle: str = Field(min_length=2, max_length=300)
    nature: Literal["creance", "dette"]
    devise: str = Field(pattern="^[A-Z]{3}$")
    montant_devise: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    valeur_comptable: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


@lru_cache
def accounts() -> dict[str, dict[str, str]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "devises.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}


def build(db: Session, file: AuditFile) -> dict[str, Any]:
    q = quantum(decimals(db, file.devise))
    rows = db.scalars(
        select(CurrencyPosition)
        .where(CurrencyPosition.audit_file_id == file.id, CurrencyPosition.deleted_at.is_(None))
        .order_by(CurrencyPosition.devise, CurrencyPosition.compte)
    )
    out, missing = [], set()
    loss = gain = ZERO
    for p in rows:
        found = find_rate(db, p.devise, file.devise, file.date_fin)
        item = {
            "id": str(p.id),
            "compte": p.compte,
            "libelle": p.libelle,
            "nature": p.nature,
            "devise": p.devise,
            "montant_devise": str(p.montant_devise),
            "valeur_comptable": str(p.valeur_comptable),
        }
        if found is None:
            missing.add(p.devise)
            out.append({**item, "cours": None, "valeur_cloture": None, "ecart": None})
            continue
        rate, rate_date = found
        value = (p.montant_devise * rate).quantize(q, ROUND_HALF_UP)
        change = value - p.valeur_comptable
        # Perte latente : créance qui baisse, dette qui monte.
        latent = -change if p.nature == "creance" else change
        if latent > 0:
            loss += latent
        else:
            gain -= latent
        out.append(
            {
                **item,
                "cours": str(rate),
                "date_cours": rate_date.isoformat(),
                "valeur_cloture": str(value),
                "ecart": str(change),
                "perte_latente": str(max(latent, ZERO)),
                "gain_latent": str(max(-latent, ZERO)),
            }
        )
    code = db.get(AccountingFramework, file.framework_id).code
    acc = accounts().get(code, {})
    books = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file)}
    provision = -sum((v for c, v in books.items() if acc and c.startswith(acc["provision"])), ZERO)
    return {
        "positions": out,
        "cours_manquants": sorted(missing),
        "pertes_latentes": str(loss),
        "gains_latents": str(gain),
        "provision_comptabilisee": str(provision),
        "provision_requise": str(loss),
        "comptes": acc,
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


@router.get("/audit-files/{file_id}/currency-positions")
def read_positions(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return build(db, file)


@router.post("/audit-files/{file_id}/currency-positions", status_code=status.HTTP_201_CREATED)
def add_position(
    file_id: uuid.UUID, body: PositionIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    compte = clean_account(body.compte)
    if not any(compte.startswith(r) for r in plan_roots(db, file.framework_id)):
        raise HTTPException(422, f"Compte {compte} hors plan")
    if body.devise == file.devise:
        raise HTTPException(422, "Opération dans la devise du dossier : pas de conversion")
    db.add(
        CurrencyPosition(
            client_id=client.id, audit_file_id=file.id, **{**body.model_dump(), "compte": compte}
        )
    )
    db.commit()
    return build(db, file)


@router.delete("/audit-files/{file_id}/currency-positions/{position_id}", status_code=204)
def delete_position(
    file_id: uuid.UUID, position_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    file, _ = _context(db, file_id, user, True)
    row = db.get(CurrencyPosition, position_id)
    if row is None or row.deleted_at is not None or row.audit_file_id != file.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable")
    row.deleted_at, row.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/audit-files/{file_id}/currency-positions/entry", status_code=status.HTTP_201_CREATED)
def conversion_entry(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, True)
    data = build(db, file)
    if data["cours_manquants"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cours de clôture manquant ({', '.join(data['cours_manquants'])} → {file.devise})",
        )
    acc = data["comptes"]
    if not acc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Comptes d'écarts de conversion non définis")
    lines = []
    for p in data["positions"]:
        loss, gain = Decimal(p["perte_latente"]), Decimal(p["gain_latent"])
        label = f"Conversion {p['devise']} : {p['libelle']}"
        # Perte : le tiers perd de la valeur à l'actif ou en gagne au passif → crédit du tiers.
        if loss > 0:
            lines += [
                {"compte": acc["ecart_actif"], "libelle": label, "debit": loss},
                {"compte": p["compte"], "libelle": label, "credit": loss},
            ]
        elif gain > 0:
            lines += [
                {"compte": p["compte"], "libelle": label, "debit": gain},
                {"compte": acc["ecart_passif"], "libelle": label, "credit": gain},
            ]
    gap = Decimal(data["provision_requise"]) - Decimal(data["provision_comptabilisee"])
    if gap > 0:
        lines += [
            {"compte": acc["dotation"], "libelle": "Provision pour perte de change", "debit": gap},
            {
                "compte": acc["provision"],
                "libelle": "Provision pour perte de change",
                "credit": gap,
            },
        ]
    elif gap < 0:
        lines += [
            {
                "compte": acc["provision"],
                "libelle": "Provision pour perte de change",
                "debit": -gap,
            },
            {
                "compte": acc["reprise"],
                "libelle": "Reprise de provision pour perte de change",
                "credit": -gap,
            },
        ]
    return propose(
        db,
        file,
        user,
        ORIGIN,
        f"Écarts de conversion et risque de change {file.exercice}",
        f"Réévaluation au cours de clôture du {file.date_fin:%d/%m/%Y} (RCO-15) : pertes latentes "
        f"{data['pertes_latentes']}, gains latents {data['gains_latents']}.",
        lines,
    )
