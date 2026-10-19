"""Révision fiscale d'une clôture : chiffre d'affaires comptable et déclaré en TVA mois par
mois (RCO-18), TVA collectée et déductible comptabilisée et déclarée, crédit de TVA justifié
par la dernière déclaration, TVA théorique au taux normal du pays (RCO-19).

Montants comptables tirés du grand livre N : chiffre d'affaires = crédits − débits des
comptes de ventes, TVA collectée = crédits − débits, TVA déductible = débits − crédits ;
déclarations importées (une ligne par mois)."""

import json
import uuid
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.api.third_parties import _ledger
from app.cabinet.fiscal import resolve
from app.cabinet.tables import read_table
from app.models.portfolio import Client, TaxReturns
from app.models.revision import AccountingFramework, AuditFile

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
RETURN_FIELDS = {
    "mois": ("periode", "période", "mois declare"),
    "ca_declare": ("chiffre d affaires", "ca", "chiffre d'affaires declare", "ca declare"),
    "tva_collectee": ("tva collectee declaree", "tva brute"),
    "tva_deductible": ("tva deductible declaree", "tva recuperable"),
    "credit_reporte": ("credit de tva", "credit a reporter", "credit reporte"),
}


@lru_cache
def roots() -> dict[str, dict[str, list[str]]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "fiscal_comptes.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}


def accounts_of(db: Session, file: AuditFile) -> dict[str, list[str]]:
    return roots().get(db.get(AccountingFramework, file.framework_id).code, {})


def month_key(value: Any) -> str | None:
    """« 2026-03 » à partir d'une date, de « 03/2026 », « 2026-03 » ou « mars 2026 »."""
    import datetime as dt
    import re

    if isinstance(value, dt.date):
        return f"{value:%Y-%m}"
    text = str(value or "").strip().lower()
    names = [
        "janv",
        "févr",
        "mars",
        "avr",
        "mai",
        "juin",
        "juil",
        "août",
        "sept",
        "oct",
        "nov",
        "déc",
    ]
    for i, n in enumerate(names, 1):
        if text.startswith(n) or text.startswith(n.replace("é", "e").replace("û", "u")):
            year = re.search(r"(\d{4})", text)
            return f"{year.group(1)}-{i:02d}" if year else None
    m = re.match(r"^(\d{4})[-/](\d{1,2})", text) or None
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})[-/](\d{4})$", text) or re.match(r"^\d{1,2}/(\d{1,2})/(\d{4})$", text)
    if m:
        month, year = (m.group(1), m.group(2))
        return f"{year}-{int(month):02d}"
    return None


def monthly(frame: pl.DataFrame, prefixes: list[str], credit_side: bool) -> dict[str, Decimal]:
    """Mouvements nets par mois des comptes commençant par l'une des racines."""
    if not prefixes:
        return {}
    rows = frame.filter(pl.any_horizontal([pl.col("compte").str.starts_with(r) for r in prefixes]))
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows.iter_rows(named=True):
        if r["date"] is None:
            continue
        net = Decimal(r["credit"] or 0) - Decimal(r["debit"] or 0)
        out[f"{r['date']:%Y-%m}"] += net if credit_side else -net
    return out


def returns_of(db: Session, file: AuditFile) -> TaxReturns | None:
    return db.scalar(
        select(TaxReturns).where(
            TaxReturns.audit_file_id == file.id, TaxReturns.deleted_at.is_(None)
        )
    )


def _months(file: AuditFile) -> list[str]:
    out, (y, m) = [], (file.date_debut.year, file.date_debut.month)
    while (y, m) <= (file.date_fin.year, file.date_fin.month):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _tolerance(db: Session, file: AuditFile) -> Decimal:
    p = resolve(db, file.pays or "", file.exercice, "tolerance_rapprochement")
    return p.valeur if p else ZERO


def turnover(db: Session, file: AuditFile) -> dict[str, Any]:
    frame = _ledger(db, file)
    acc = accounts_of(db, file)
    books = monthly(frame, acc.get("chiffre_affaires", []), True)
    tr = returns_of(db, file)
    declared = {r["mois"]: Decimal(r.get("ca_declare") or 0) for r in (tr.tva if tr else [])}
    tol = _tolerance(db, file)
    rows = []
    for month in _months(file):
        b, d = books.get(month, ZERO), declared.get(month)
        gap = b - d if d is not None else None
        rows.append(
            {
                "mois": month,
                "comptable": str(b),
                "declare": str(d) if d is not None else None,
                "ecart": str(gap) if gap is not None else None,
                "concordant": gap is not None and abs(gap) <= tol,
            }
        )
    total_b = sum((Decimal(r["comptable"]) for r in rows), ZERO)
    total_d = sum((Decimal(r["declare"]) for r in rows if r["declare"]), ZERO)
    return {
        "mois": rows,
        "total_comptable": str(total_b),
        "total_declare": str(total_d),
        "ecart_total": str(total_b - total_d),
        "tolerance": str(tol),
        "mois_sans_declaration": [r["mois"] for r in rows if r["declare"] is None],
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


@router.post("/audit-files/{file_id}/tax-returns", status_code=status.HTTP_201_CREATED)
async def upload_returns(
    file_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Déclarations de TVA de l'exercice : mois, chiffre d'affaires déclaré, TVA collectée,
    TVA déductible, crédit reporté ; un nouvel import remplace le précédent."""
    audit_file, client = _context(db, file_id, user, True)
    rows = read_table(
        await file.read(),
        file.filename or "x.csv",
        RETURN_FIELDS,
        ("mois", "ca_declare"),
        amounts=("ca_declare", "tva_collectee", "tva_deductible", "credit_reporte"),
    )
    for r in rows:
        key = month_key(r["mois"])
        if key is None:
            raise HTTPException(422, f"Mois illisible « {r['mois']} »")
        r["mois"] = key
    tr = returns_of(db, audit_file)
    if tr is None:
        tr = TaxReturns(client_id=client.id, audit_file_id=audit_file.id)
        db.add(tr)
    tr.tva, tr.fichier = rows, file.filename
    db.commit()
    return {"lignes": len(rows), "fichier": file.filename}


@router.get("/audit-files/{file_id}/turnover-reconciliation")
def read_turnover(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return turnover(db, file)


def _compare(
    months: list[str], books: dict[str, Decimal], declared: dict[str, Decimal], tol: Decimal
) -> list[dict[str, Any]]:
    rows = []
    for month in months:
        b, d = books.get(month, ZERO), declared.get(month)
        gap = b - d if d is not None else None
        rows.append(
            {
                "mois": month,
                "comptable": str(b),
                "declare": str(d) if d is not None else None,
                "ecart": str(gap) if gap is not None else None,
                "concordant": gap is not None and abs(gap) <= tol,
            }
        )
    return rows


def vat(db: Session, file: AuditFile) -> dict[str, Any]:
    from app.revision.mapping import assignments

    frame = _ledger(db, file)
    acc = accounts_of(db, file)
    tr = returns_of(db, file)
    lines = sorted(tr.tva if tr else [], key=lambda r: r["mois"])
    tol = _tolerance(db, file)
    months = _months(file)

    def declared(field: str) -> dict[str, Decimal]:
        return {r["mois"]: Decimal(r[field]) for r in lines if r.get(field) not in (None, "")}

    collected = _compare(
        months, monthly(frame, acc.get("tva_collectee", []), True), declared("tva_collectee"), tol
    )
    deductible = _compare(
        months,
        monthly(frame, acc.get("tva_deductible", []), False),
        declared("tva_deductible"),
        tol,
    )
    rate = resolve(db, file.pays or "", file.exercice, "taux_tva_normal")
    turnover_total = sum(monthly(frame, acc.get("chiffre_affaires", []), True).values(), ZERO)
    collected_total = sum((Decimal(r["comptable"]) for r in collected), ZERO)
    theoretical = (turnover_total * rate.valeur / 100).quantize(Decimal("0.01")) if rate else None
    books = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file)}
    credit = sum(
        (v for c, v in books.items() if any(c.startswith(r) for r in acc.get("credit_tva", []))),
        ZERO,
    )
    last = lines[-1] if lines else None
    reported = (
        Decimal(last["credit_reporte"])
        if last and last.get("credit_reporte") not in (None, "")
        else None
    )
    return {
        "collectee": collected,
        "deductible": deductible,
        "tva_theorique": str(theoretical) if theoretical is not None else None,
        "taux_tva": format(rate.valeur.normalize(), "f") if rate else None,
        "tva_collectee_totale": str(collected_total),
        "ecart_theorique": str(collected_total - theoretical) if theoretical is not None else None,
        "credit_tva": {
            "solde_comptable": str(credit),
            "credit_declare": str(reported) if reported is not None else None,
            "mois_declaration": last["mois"] if last else None,
            "ecart": str(credit - reported) if reported is not None else None,
            "justifie": reported is not None and abs(credit - reported) <= tol,
        },
        "tolerance": str(tol),
    }


@router.get("/audit-files/{file_id}/vat-reconciliation")
def read_vat(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return vat(db, file)
