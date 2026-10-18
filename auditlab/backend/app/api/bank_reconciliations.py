"""Rapprochements bancaires importés et contrôlés (REV-20)."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models.revision import AuditFile, BankReconciliation, BankReconciliationItem, Confirmation
from app.revision import bank
from app.revision.balances import ImportError_, clean_account, parse_amount
from app.revision.mapping import assignments

router = APIRouter(tags=["Révision – rapprochements bancaires"])
ZERO = Decimal(0)
MAX_BYTES = 20 * 1024 * 1024


def _active(db: Session, file_id: uuid.UUID) -> list[BankReconciliation]:
    return list(
        db.scalars(
            select(BankReconciliation)
            .where(
                BankReconciliation.audit_file_id == file_id, BankReconciliation.deleted_at.is_(None)
            )
            .order_by(BankReconciliation.compte)
        )
    )


def overview(db: Session, file: AuditFile) -> dict[str, Any]:
    s = get_settings()
    books = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file)}
    confirmations = {
        c.compte: c.solde_confirme
        for c in db.scalars(
            select(Confirmation).where(
                Confirmation.audit_file_id == file.id,
                Confirmation.type == "banque",
                Confirmation.deleted_at.is_(None),
                Confirmation.solde_confirme.is_not(None),
            )
        )
    }
    trivial = file.seuil_insignifiant or ZERO
    rows = []
    for rec in _active(db, file.id):
        items = list(
            db.scalars(
                select(BankReconciliationItem)
                .where(BankReconciliationItem.reconciliation_id == rec.id)
                .order_by(BankReconciliationItem.date)
            )
        )
        book = books.get(rec.compte, ZERO)
        checks = bank.controls(
            rec.solde_releve,
            book,
            items,
            rec.date_releve,
            file.date_fin,
            s.anciennete_suspens_jours,
            trivial,
            confirmations.get(rec.compte),
        )
        limit = file.date_fin - dt.timedelta(days=s.anciennete_suspens_jours)
        rows.append(
            {
                "id": str(rec.id),
                "compte": rec.compte,
                "date_releve": rec.date_releve.isoformat(),
                "nom_fichier": rec.nom_fichier,
                "solde_releve": f"{rec.solde_releve:.2f}",
                "solde_comptable": str(book),
                "non_rapproche": str(checks["non_rapproche"]),
                "operations_releve": str(checks["operations_releve"]),
                "suspens_anciens": checks["suspens_anciens"],
                "anomalies": checks["anomalies"],
                "avertissements": checks["avertissements"],
                "suspens": [
                    {
                        "date": i.date.isoformat() if i.date else None,
                        "libelle": i.libelle,
                        "reference": i.reference,
                        "origine": i.origine,
                        "montant": str(i.montant),
                        "ancien": i.date is not None and i.date < limit,
                    }
                    for i in items
                ],
            }
        )
    roots = s.racines_banques
    missing = sorted(
        c
        for c, v in books.items()
        if any(c.startswith(r) for r in roots) and c not in {r["compte"] for r in rows}
    )
    return {"rapprochements": rows, "comptes_sans_rapprochement": missing}


@router.get("/audit-files/{file_id}/bank-reconciliations")
def list_reconciliations(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return overview(db, file)


@router.post("/audit-files/{file_id}/bank-reconciliations", status_code=status.HTTP_201_CREATED)
def import_reconciliation(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    compte: str = Form(...),
    solde_releve: str = Form(...),
    date_releve: dt.date | None = Form(None),
    file: UploadFile | None = None,
) -> dict[str, Any]:
    audit_file, engagement = get_file(db, file_id, user)
    require_work(audit_file, engagement, user)
    account = clean_account(compte)
    if not any(account.startswith(r) for r in get_settings().racines_banques):
        raise HTTPException(
            422, "Compte de trésorerie attendu (banques, établissements financiers)"
        )
    content, name = b"", None
    try:
        statement = parse_amount(solde_releve)
        items = []
        if file is not None and file.filename:
            content = file.file.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ImportError_("Fichier trop volumineux")
            name = PurePath(file.filename).name[:255]
            items = bank.parse_items(content, name)
    except ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    now = dt.datetime.now(dt.UTC)
    for previous in _active(db, audit_file.id):
        if previous.compte == account:
            previous.deleted_at, previous.deleted_by = now, user.id
    rec = BankReconciliation(
        engagement_id=audit_file.engagement_id,
        audit_file_id=audit_file.id,
        compte=account,
        date_releve=date_releve or audit_file.date_fin,
        solde_releve=statement,
        nom_fichier=name,
        sha256=hashlib.sha256(content).hexdigest() if content else None,
    )
    db.add(rec)
    db.flush()
    db.add_all(BankReconciliationItem(reconciliation_id=rec.id, **i) for i in items)
    db.commit()
    return overview(db, audit_file)
