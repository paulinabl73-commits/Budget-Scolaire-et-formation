"""Ratios financiers comparés sur trois exercices (REV-13).

Les formules et familles (liquidité, solvabilité, rentabilité, délais clients et fournisseurs)
sont des données du référentiel. N et N-1 proviennent du dossier ; N-2 de la balance N-1 du
dossier de l'exercice précédent, lorsqu'il existe et que ses états peuvent être produits.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession
from app.api.mapping import values_or_409
from app.models.revision import AccountingFramework, AuditFile
from app.revision.formula import evaluate
from app.revision.mapping import UnmappedError, file_values

router = APIRouter(tags=["Révision – ratios"])
PRECISION = {"pourcentage": Decimal("0.01"), "jours": Decimal("1"), "ratio": Decimal("0.01")}


def _ratio(formula: str, values: dict[str, Decimal] | None, unit: str) -> str | None:
    if values is None:
        return None
    result = evaluate(formula, values)
    if result is None:
        return None  # division par zéro : ratio non significatif
    if unit == "pourcentage":
        result *= 100
    return str(result.quantize(PRECISION.get(unit, Decimal("0.01")), ROUND_HALF_UP))


def _older(db: Session, file: AuditFile) -> dict[str, Decimal] | None:
    previous = db.get(AuditFile, file.precedent_id) if file.precedent_id else None
    if previous is None or previous.deleted_at is not None:
        return None
    try:
        return file_values(db, previous)["N-1"]
    except UnmappedError:
        return None


@router.get("/audit-files/{file_id}/ratios")
def read_ratios(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    values = values_or_409(db, file)
    has_n1 = any(values["N-1"].values())
    columns = {"N": values["N"], "N-1": values["N-1"] if has_n1 else None, "N-2": _older(db, file)}
    fw = db.get(AccountingFramework, file.framework_id)
    return {
        "exercices": [
            {"periode": p, "exercice": file.exercice - i, "disponible": columns[p] is not None}
            for i, p in enumerate(columns)
        ],
        "ratios": [
            {
                "code": r["code"],
                "libelle": r["libelle"],
                "famille": r.get("famille"),
                "unite": r.get("unite", "ratio"),
                "valeurs": {
                    p: _ratio(r["formule"], v, r.get("unite", "ratio")) for p, v in columns.items()
                },
            }  # fmt: skip
            for r in fw.ratios
        ],
    }
