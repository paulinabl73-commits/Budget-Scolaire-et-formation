"""Écritures d'inventaire générées par les assistants du Module 6 (RCO-11 à RCO-16).

Chaque assistant propose une écriture d'ajustement de type « inventaire » marquée de son
origine ; tant qu'elle est proposée, une nouvelle génération la remplace. Acceptée, elle entre
dans les soldes révisés (REV-21) et s'exporte vers le logiciel du client (RCO-17).
"""

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.revision import Adjustment, AuditFile
from app.models.user import User


def generated(db: Session, file: AuditFile, origine: str) -> Adjustment | None:
    return db.scalar(
        select(Adjustment).where(
            Adjustment.audit_file_id == file.id,
            Adjustment.origine == origine,
            Adjustment.deleted_at.is_(None),
        )
    )


def merge(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Regroupe les lignes par compte et par sens ; écarte les montants nuls."""
    out: dict[tuple[str, str], Decimal] = {}
    labels: dict[tuple[str, str], str | None] = {}
    for ln in lines:
        for side in ("debit", "credit"):
            amount = Decimal(ln.get(side) or 0)
            if amount:
                key = (ln["compte"], side)
                out[key] = out.get(key, Decimal(0)) + amount
                labels.setdefault(key, ln.get("libelle"))
    return [
        {"compte": c, "libelle": labels[(c, side)], side: str(v)}
        for (c, side), v in sorted(out.items(), key=lambda x: (x[0][1] != "debit", x[0][0]))
        if v
    ]


def propose(
    db: Session,
    file: AuditFile,
    user: User,
    origine: str,
    libelle: str,
    justification: str,
    lines: list[dict[str, Any]],
    date: dt.date | None = None,
) -> dict[str, Any]:
    from app.api.adjustments import AdjustmentIn, create_adjustment

    lines = merge(lines)
    if len(lines) < 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun montant : pas d'écriture à générer")
    previous = generated(db, file, origine)
    if previous is not None:
        if previous.statut != "proposee":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Écriture {origine} déjà {previous.statut} (AJE {previous.numero}) : "
                "supprimez-la ou refusez-la avant de la régénérer",
            )
        previous.deleted_at, previous.deleted_by = dt.datetime.now(dt.UTC), user.id
        db.flush()
    entry = AdjustmentIn(
        type="inventaire",
        origine=origine,
        date_ecriture=date or file.date_fin,
        libelle=libelle,
        justification=justification,
        lignes=lines,
    )
    return create_adjustment(file.id, entry, user, db)
