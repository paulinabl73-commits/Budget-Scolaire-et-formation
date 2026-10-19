"""Rapprochements d'une clôture (RCO-10) : comptes de tiers avec les balances auxiliaires,
comptes bancaires avec les relevés (rapprochements bancaires du REV-20)."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter

from app.api.audit_files import get_file
from app.api.bank_reconciliations import overview as bank_overview
from app.api.deps import CurrentUser, DbSession
from app.revision.imports import TYPES, active_balance, balance_lines

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)


@router.get("/audit-files/{file_id}/reconciliations")
def reconciliations(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    general = balance_lines(db, active_balance(db, file.id, "N"))
    aux_rows = [
        tb for t in TYPES if t.startswith("aux_") if (tb := active_balance(db, file.id, "N", t))
    ]
    tiers = []
    for tb in aux_rows:
        root = tb.compte_collectif or ""
        lines = balance_lines(db, tb)
        aux = sum((ln.net("solde") for ln in lines), ZERO)
        control = sum((ln.net("solde") for ln in general if ln.compte.startswith(root)), ZERO)
        tiers.append(
            {
                "type": tb.type,
                "compte_collectif": root,
                "nombre_tiers": len(lines),
                "total_auxiliaire": str(aux),
                "solde_collectif": str(control),
                "ecart": str(control - aux),
                "rapproche": control == aux,
                "tiers": [
                    {"code": ln.compte, "libelle": ln.libelle, "solde": str(ln.net("solde"))}
                    for ln in sorted(lines, key=lambda x: -abs(x.net("solde")))[:500]
                ],
            }
        )
    return {
        "balance_generale": bool(general),
        "auxiliaires": tiers,
        "banques": bank_overview(db, file),
    }
