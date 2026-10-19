"""Rapprochement des salaires comptabilisés avec les déclarations sociales et fiscales
(RCO-21), mois par mois : masse salariale, cotisations sociales, impôts sur salaires ;
cotisations et impôts théoriques aux taux du pays (RCO-22) lorsqu'ils sont saisis."""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.tax_review import (
    _compare,
    _context,
    _months,
    _tolerance,
    accounts_of,
    month_key,
    monthly,
    returns_of,
)
from app.api.third_parties import _ledger
from app.cabinet.fiscal import resolve
from app.cabinet.tables import read_table
from app.models.portfolio import TaxReturns
from app.models.revision import AuditFile

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
FIELDS = {
    "mois": ("periode", "période"),
    "masse_salariale": ("salaires bruts", "masse salariale declaree", "salaires"),
    "cotisations": ("cotisations sociales", "cotisations declarees", "charges sociales"),
    "impots_salaires": ("impots sur salaires", "its", "impots et taxes sur salaires"),
}


def payroll(db: Session, file: AuditFile) -> dict[str, Any]:
    frame = _ledger(db, file)
    acc = accounts_of(db, file)
    tr = returns_of(db, file)
    lines = tr.social if tr else []
    tol = _tolerance(db, file)
    months = _months(file)

    def declared(field: str) -> dict[str, Decimal]:
        return {r["mois"]: Decimal(r[field]) for r in lines if r.get(field) not in (None, "")}

    out: dict[str, Any] = {"tolerance": str(tol)}
    books = {}
    for key, root_key in (
        ("masse_salariale", "salaires"),
        ("cotisations", "charges_sociales"),
        ("impots_salaires", "impots_salaires"),
    ):
        books[key] = monthly(frame, acc.get(root_key, []), False)
        out[key] = _compare(months, books[key], declared(key), tol)
    wages = sum(books["masse_salariale"].values(), ZERO)
    theory = {}
    for key, code in (
        ("cotisations", "taux_cotisations_patronales"),
        ("impots_salaires", "taux_impots_salaires"),
    ):
        p = resolve(db, file.pays or "", file.exercice, code)
        booked = sum(books[key].values(), ZERO)
        if p is None:
            theory[key] = {
                "taux": None,
                "theorique": None,
                "comptabilise": str(booked),
                "ecart": None,
            }
        else:
            expected = (wages * p.valeur / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
            theory[key] = {
                "taux": format(p.valeur.normalize(), "f"),
                "theorique": str(expected),
                "comptabilise": str(booked),
                "ecart": str(booked - expected),
            }
    out["masse_salariale_totale"] = str(wages)
    out["theorique"] = theory
    return out


@router.post("/audit-files/{file_id}/payroll-returns", status_code=status.HTTP_201_CREATED)
async def upload_payroll(
    file_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Déclarations sociales et fiscales sur salaires de l'exercice : mois, masse salariale,
    cotisations sociales, impôts sur salaires ; un nouvel import remplace le précédent."""
    audit_file, client = _context(db, file_id, user, True)
    rows = read_table(
        await file.read(),
        file.filename or "x.csv",
        FIELDS,
        ("mois", "masse_salariale"),
        amounts=("masse_salariale", "cotisations", "impots_salaires"),
    )
    for r in rows:
        key = month_key(r["mois"])
        if key is None:
            raise HTTPException(422, f"Mois illisible « {r['mois']} »")
        r["mois"] = key
    tr = returns_of(db, audit_file)
    if tr is None:
        tr = TaxReturns(client_id=client.id, audit_file_id=audit_file.id, tva=[])
        db.add(tr)
    tr.social, tr.fichier_social = rows, file.filename
    db.commit()
    return {"lignes": len(rows), "fichier": file.filename}


@router.get("/audit-files/{file_id}/payroll-reconciliation")
def read_payroll(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return payroll(db, file)
