"""Revue analytique N/N-1 (REV-12) : variation en valeur et en % par poste et par compte,
signalement des variations significatives, justification obligatoire de chacune.

Une variation est signalée si elle dépasse le seuil de planification, ou si elle dépasse à la
fois le pourcentage de variation retenu et le seuil d'insignifiance (un poste nouveau ou
disparu compte comme une variation de 100 %). Le seuil (REV-11) doit être fixé.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.mapping import assignable, values_or_409
from app.models.revision import AnalyticalJustification, AuditFile
from app.revision.mapping import assignments, postes

router = APIRouter(tags=["Révision – revue analytique"])
ZERO = Decimal(0)


class JustificationIn(BaseModel):
    niveau: str = Field(pattern="^(poste|compte)$")
    code: str = Field(min_length=1, max_length=30)
    texte: str = Field(min_length=10, max_length=5000)


def _justifications(db: Session, file_id: uuid.UUID) -> dict[tuple[str, str], Any]:
    rows = db.scalars(
        select(AnalyticalJustification).where(
            AnalyticalJustification.audit_file_id == file_id,
            AnalyticalJustification.deleted_at.is_(None),
        )
    )
    return {(j.niveau, j.code): j for j in rows}


def _line(file: AuditFile, niveau: str, code: str, libelle: str | None, n: Decimal,
          n1: Decimal, flaggable: bool, notes: dict) -> dict[str, Any]:  # fmt: skip
    delta = n - n1
    pct = (delta / abs(n1) * 100).quantize(Decimal("0.1"), ROUND_HALF_UP) if n1 else None
    pct_abs = abs(pct) if pct is not None else (Decimal(100) if delta else ZERO)
    flagged = flaggable and (
        abs(delta) > file.seuil_planification
        or (pct_abs > file.seuil_variation_pct and abs(delta) > file.seuil_insignifiant)
    )
    note = notes.get((niveau, code))
    return {
        "niveau": niveau, "code": code, "libelle": libelle, "N": str(n), "N-1": str(n1),
        "variation": str(delta), "variation_pct": str(pct) if pct is not None else None,
        "signale": flagged,
        "justification": note.texte if note else None,
        "justifie_le": note.updated_at.isoformat() if note else None,
    }  # fmt: skip


def review(db: Session, file: AuditFile) -> dict[str, Any]:
    if file.seuil_signification is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Fixez d'abord le seuil de signification (planification)"
        )
    values = values_or_409(db, file)
    notes = _justifications(db, file.id)
    lines = [
        _line(file, "poste", ln.code, ln.libelle, values["N"].get(ln.code, ZERO),
              values["N-1"].get(ln.code, ZERO), assignable(ln), notes) | {"etat": ln.etat,
              "total": not assignable(ln)}
        for ln in postes(db, file.framework_id)
    ]  # fmt: skip
    accounts = [
        _line(file, "compte", a.compte, a.libelle, a.soldes.get("N", ZERO),
              a.soldes.get("N-1", ZERO), True, notes)
        for a in assignments(db, file)
    ]  # fmt: skip
    flagged = [x for x in lines + accounts if x["signale"]]
    return {
        "seuils": {
            "planification": str(file.seuil_planification),
            "insignifiant": str(file.seuil_insignifiant),
            "variation_pct": str(file.seuil_variation_pct),
        },
        "postes": lines,
        "comptes": accounts,
        "nb_signales": len(flagged),
        "nb_non_justifies": sum(1 for x in flagged if not x["justification"]),
    }


@router.get("/audit-files/{file_id}/analytical-review")
def read_review(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return review(db, file)


@router.put("/audit-files/{file_id}/analytical-review/justifications")
def justify(
    file_id: uuid.UUID, body: JustificationIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    result = review(db, file)
    known = {(x["niveau"], x["code"]) for x in result["postes"] + result["comptes"]}
    if (body.niveau, body.code) not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ligne inconnue de la revue analytique")
    note = _justifications(db, file.id).get((body.niveau, body.code))
    if note is None:
        note = AnalyticalJustification(
            engagement_id=file.engagement_id, audit_file_id=file.id, niveau=body.niveau,
            code=body.code, texte=body.texte,
        )  # fmt: skip
        db.add(note)
    note.texte = body.texte
    db.commit()
    return review(db, file)
