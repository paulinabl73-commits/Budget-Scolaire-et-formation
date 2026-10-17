"""Comptes de tiers : lettrage, justification, balance âgée et dépréciation (REV-18)."""

import uuid
from decimal import Decimal
from typing import Any

import polars as pl
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_direct, require_work
from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models.data import Dataset
from app.models.revision import Adjustment, AdjustmentLine, AuditFile
from app.revision.currency import decimals, quantum
from app.revision.imports import active_balance
from app.revision.mapping import assignments
from app.revision.third_parties import aging, match

router = APIRouter(tags=["Révision – comptes de tiers"])
ZERO = Decimal(0)


class GridIn(BaseModel):
    grille: list[tuple[int, Decimal]] = Field(min_length=1, max_length=20)
    tva_pct: Decimal | None = Field(default=None, ge=0, le=100)


def _ledger(db: Session, file: AuditFile) -> pl.DataFrame:
    from app.analytics.store import data_dir

    gl = active_balance(db, file.id, "N", "grand_livre")
    if gl is None or gl.dataset_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun grand livre N accepté")
    return pl.read_parquet(data_dir() / db.get(Dataset, gl.dataset_id).chemin_parquet)


def _grid(file: AuditFile) -> list[list[float]]:
    return file.grille_depreciation or get_settings().grille_depreciation_defaut


def _recorded_impairment(db: Session, file: AuditFile) -> Decimal:
    """Dépréciation comptabilisée (solde créditeur révisé des comptes 491)."""
    root = get_settings().racine_depreciation_clients
    items = assignments(db, file, adjusted=True)
    return -sum((a.soldes.get("N", ZERO) for a in items if a.compte.startswith(root)), ZERO)


@router.get("/audit-files/{file_id}/third-parties")
def justification(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    states = match(_ledger(db, file), get_settings().racines_tiers)
    balances = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file)}
    rows = []
    for compte, s in sorted(states.items()):
        balance = balances.get(compte, ZERO)
        rows.append(
            {
                "compte": compte,
                "mode": s.mode,
                "lettrees": s.lettrees,
                "ouvertes": len(s.ouvertes),
                "solde_balance": str(balance),
                "solde_ouvert": str(s.solde_ouvert),
                "ecart": str(balance - s.solde_ouvert),
                "justifie": balance == s.solde_ouvert,
                "anomalies": s.anomalies,
                "lignes_ouvertes": [
                    {
                        "date": i.date.isoformat() if i.date else None,
                        "piece": i.piece,
                        "libelle": i.libelle,
                        "tiers": i.tiers,
                        "montant": str(i.net),
                    }
                    for i in s.ouvertes[:200]
                ],
            }
        )
    return {"comptes": rows, "non_justifies": sum(1 for r in rows if not r["justifie"])}


@router.get("/audit-files/{file_id}/receivables-aging")
def receivables_aging(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    states = match(_ledger(db, file), get_settings().racines_clients)
    result = aging(
        states, file.date_fin, _grid(file), file.tva_depreciation, decimals(db, file.devise)
    )
    q = quantum(decimals(db, file.devise))
    recorded = _recorded_impairment(db, file).quantize(q)
    required = Decimal(result["depreciation_requise"])
    vat = file.tva_depreciation
    return {
        **result,
        "grille": _grid(file),
        "tva_pct": str(vat) if vat is not None else None,
        "depreciation_comptabilisee": str(recorded),
        "ecart": str((required - recorded).quantize(q)),
    }


@router.put("/audit-files/{file_id}/impairment-grid")
def set_grid(file_id: uuid.UUID, body: GridIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_direct(file, engagement, user)
    days = [d for d, _ in body.grille]
    if days[0] != 0 or days != sorted(set(days)) or any(not 0 <= r <= 100 for _, r in body.grille):
        raise HTTPException(
            422, "Grille : anciennetés croissantes depuis 0 jour, taux de 0 à 100 %"
        )
    file.grille_depreciation = [[d, float(r)] for d, r in body.grille]
    file.tva_depreciation = body.tva_pct
    db.commit()
    return receivables_aging(file_id, user, db)


@router.post("/audit-files/{file_id}/receivables-aging/adjustment", status_code=201)
def propose_adjustment(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Propose l'écriture (REV-21) qui porte la dépréciation au niveau requis par la grille."""
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    gap = Decimal(receivables_aging(file_id, user, db)["ecart"])
    if gap == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Dépréciation comptabilisée conforme à la grille"
        )
    s = get_settings()
    if gap > 0:
        debit, credit, label = (
            s.compte_dotation_creances,
            s.compte_depreciation_clients,
            "Complément",
        )
    else:
        debit, credit, label = s.compte_depreciation_clients, s.compte_reprise_creances, "Reprise"
    last = db.scalar(select(func.max(Adjustment.numero)).where(Adjustment.audit_file_id == file.id))
    adj = Adjustment(
        engagement_id=file.engagement_id,
        audit_file_id=file.id,
        numero=(last or 0) + 1,
        type="correction",
        libelle=f"{label} de dépréciation des créances clients",
        justification="Écart entre la dépréciation comptabilisée et celle qui résulte de la "
        "balance âgée et de la grille de dépréciation du dossier (REV-18).",
    )
    db.add(adj)
    db.flush()
    db.add_all(
        [
            AdjustmentLine(adjustment_id=adj.id, compte=debit, debit=abs(gap)),
            AdjustmentLine(adjustment_id=adj.id, compte=credit, credit=abs(gap)),
        ]
    )
    db.commit()
    return {"id": str(adj.id), "numero": adj.numero, "montant": str(abs(gap))}
