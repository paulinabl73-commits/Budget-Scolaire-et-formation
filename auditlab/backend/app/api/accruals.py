"""Rattachement des charges et produits à l'exercice (RCO-13) : charges à payer, produits à
recevoir, charges et produits constatés d'avance ; reprise à l'ouverture de N+1.

Constaté d'avance : part d'un montant couvrant une période qui dépasse la clôture, au
prorata des jours postérieurs à la clôture. Reprise : contre-passation, dans le dossier N+1,
de l'écriture de rattachement acceptée en N (proposée automatiquement à l'ouverture)."""

import datetime as dt
import json
import uuid
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import ON_CREATE, get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.cabinet.entries import generated, propose
from app.models.portfolio import Accrual, Client
from app.models.revision import AccountingFramework, Adjustment, AdjustmentLine, AuditFile
from app.revision.balances import clean_account
from app.revision.controls import plan_roots
from app.revision.currency import decimals, quantum

router = APIRouter(tags=["Portefeuille (Module 6)"])
ORIGIN = "RCO-13"
REVERSAL = "RCO-13-reprise"
TYPES = (
    "charge_a_payer",
    "produit_a_recevoir",
    "charge_constatee_avance",
    "produit_constate_avance",
)
# Sens de l'écriture : le compte de gestion est débité pour une charge à payer et un produit
# constaté d'avance, crédité pour un produit à recevoir et une charge constatée d'avance.
GESTION_DEBIT = {"charge_a_payer", "produit_constate_avance"}


class AccrualIn(BaseModel):
    type: Literal[TYPES]  # type: ignore[valid-type]
    libelle: str = Field(min_length=2, max_length=300)
    compte_gestion: str = Field(min_length=2, max_length=30)
    compte_tiers: str | None = Field(default=None, max_length=30)
    montant: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    montant_total: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    periode_debut: dt.date | None = None
    periode_fin: dt.date | None = None

    @model_validator(mode="after")
    def _amount(self) -> "AccrualIn":
        prorata = self.montant_total and self.periode_debut and self.periode_fin
        if self.montant is None and not prorata:
            raise ValueError("Montant, ou montant total et période couverte, obligatoires")
        if prorata and self.periode_fin < self.periode_debut:  # type: ignore[operator]
            raise ValueError("Période couverte incohérente")
        return self


@lru_cache
def default_accounts() -> dict[str, dict[str, str]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "rattachement.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}


def deferred(total: Decimal, start: dt.date, end: dt.date, closing: dt.date, q: Decimal) -> Decimal:
    """Part postérieure à la clôture d'un montant couvrant [start, end] (prorata en jours)."""
    days = (end - start).days + 1
    after = max(0, (end - max(closing + dt.timedelta(days=1), start)).days + 1)
    return (total * after / days).quantize(q, ROUND_HALF_UP)


def listing(db: Session, file: AuditFile) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Accrual)
            .where(Accrual.audit_file_id == file.id, Accrual.deleted_at.is_(None))
            .order_by(Accrual.type, Accrual.libelle)
        )
    )
    code = db.get(AccountingFramework, file.framework_id).code
    return {
        "elements": [
            {
                "id": str(a.id),
                "type": a.type,
                "libelle": a.libelle,
                "compte_gestion": a.compte_gestion,
                "compte_tiers": a.compte_tiers,
                "montant": str(a.montant),
                "montant_total": str(a.montant_total) if a.montant_total is not None else None,
                "periode_debut": a.periode_debut.isoformat() if a.periode_debut else None,
                "periode_fin": a.periode_fin.isoformat() if a.periode_fin else None,
            }
            for a in rows
        ],
        "totaux": {
            t: str(sum((a.montant for a in rows if a.type == t), Decimal(0))) for t in TYPES
        },
        "comptes_proposes": default_accounts().get(code, {}),
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


@router.get("/audit-files/{file_id}/accruals")
def read_accruals(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return listing(db, file)


@router.post("/audit-files/{file_id}/accruals", status_code=status.HTTP_201_CREATED)
def add_accrual(
    file_id: uuid.UUID, body: AccrualIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    code = db.get(AccountingFramework, file.framework_id).code
    tiers = clean_account(body.compte_tiers or default_accounts().get(code, {}).get(body.type, ""))
    gestion = clean_account(body.compte_gestion)
    roots = plan_roots(db, file.framework_id)
    for compte in (gestion, tiers):
        if not compte or not any(compte.startswith(r) for r in roots):
            raise HTTPException(422, f"Compte {compte or '(vide)'} hors plan")
    amount = body.montant
    if amount is None:
        amount = deferred(
            body.montant_total,
            body.periode_debut,
            body.periode_fin,
            file.date_fin,
            quantum(decimals(db, file.devise)),
        )  # type: ignore[arg-type]
        if amount <= 0:
            raise HTTPException(422, "Aucune part de la période après la clôture")
    db.add(
        Accrual(
            client_id=client.id,
            audit_file_id=file.id,
            type=body.type,
            libelle=body.libelle,
            compte_gestion=gestion,
            compte_tiers=tiers,
            montant=amount,
            montant_total=body.montant_total,
            periode_debut=body.periode_debut,
            periode_fin=body.periode_fin,
        )
    )
    db.commit()
    return listing(db, file)


@router.delete("/audit-files/{file_id}/accruals/{accrual_id}", status_code=204)
def delete_accrual(
    file_id: uuid.UUID, accrual_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    file, _ = _context(db, file_id, user, True)
    row = db.get(Accrual, accrual_id)
    if row is None or row.deleted_at is not None or row.audit_file_id != file.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Élément introuvable")
    row.deleted_at, row.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/audit-files/{file_id}/accruals/entry", status_code=status.HTTP_201_CREATED)
def accrual_entry(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, True)
    items = listing(db, file)["elements"]
    lines = []
    for a in items:
        debit, credit = (
            (a["compte_gestion"], a["compte_tiers"])
            if a["type"] in GESTION_DEBIT
            else (a["compte_tiers"], a["compte_gestion"])
        )
        lines += [
            {"compte": debit, "libelle": a["libelle"], "debit": a["montant"]},
            {"compte": credit, "libelle": a["libelle"], "credit": a["montant"]},
        ]
    return propose(
        db,
        file,
        user,
        ORIGIN,
        f"Rattachement des charges et produits à l'exercice {file.exercice}",
        f"Charges à payer, produits à recevoir et comptes de régularisation (RCO-13) : "
        f"{len(items)} élément(s).",
        lines,
    )


def reversal_lines(db: Session, previous: AuditFile) -> list[dict[str, Any]]:
    entry = db.scalar(
        select(Adjustment).where(
            Adjustment.audit_file_id == previous.id,
            Adjustment.origine == ORIGIN,
            Adjustment.statut == "acceptee",
            Adjustment.deleted_at.is_(None),
        )
    )
    if entry is None:
        return []
    rows = db.scalars(select(AdjustmentLine).where(AdjustmentLine.adjustment_id == entry.id))
    return [
        {
            "compte": r.compte,
            "libelle": f"Reprise : {r.libelle or ''}".strip(),
            "debit": r.credit,
            "credit": r.debit,
        }
        for r in rows
    ]


@router.post("/audit-files/{file_id}/accruals/reversal", status_code=status.HTTP_201_CREATED)
def reversal(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Contre-passation à l'ouverture des rattachements acceptés de l'exercice précédent."""
    file, _ = _context(db, file_id, user, True)
    previous = db.get(AuditFile, file.precedent_id) if file.precedent_id else None
    lines = reversal_lines(db, previous) if previous else []
    if not lines:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Aucun rattachement accepté en N-1 à reprendre"
        )
    return propose(
        db,
        file,
        user,
        REVERSAL,
        f"Reprise des rattachements de l'exercice {previous.exercice}",  # type: ignore[union-attr]
        "Contre-passation à l'ouverture des charges et produits rattachés à l'exercice "
        "précédent (RCO-13).",
        lines,
        date=file.date_debut,
    )


def _auto_reversal(db: Session, file: AuditFile, previous: AuditFile) -> None:
    """À l'ouverture du dossier N+1, propose la reprise des rattachements acceptés en N."""
    from sqlalchemy import func

    from app.api.adjustments import LineIn, _write_lines
    from app.cabinet.entries import merge

    lines = reversal_lines(db, previous)
    if not lines or generated(db, file, REVERSAL) is not None:
        return
    last = db.scalar(select(func.max(Adjustment.numero)).where(Adjustment.audit_file_id == file.id))
    adj = Adjustment(
        engagement_id=file.engagement_id,
        audit_file_id=file.id,
        numero=(last or 0) + 1,
        type="inventaire",
        origine=REVERSAL,
        date_ecriture=file.date_debut,
        libelle=f"Reprise des rattachements de l'exercice {previous.exercice}",
        justification="Contre-passation automatique à l'ouverture des charges et produits "
        "rattachés à l'exercice précédent (RCO-13).",
    )
    db.add(adj)
    db.flush()
    _write_lines(db, adj, [LineIn(**ln) for ln in merge(lines)])


ON_CREATE.append(_auto_reversal)
