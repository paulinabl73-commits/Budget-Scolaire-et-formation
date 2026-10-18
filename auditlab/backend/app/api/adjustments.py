"""Propositions d'écritures d'ajustement (REV-21).

Une écriture est équilibrée, porte sur des comptes du référentiel, est justifiée et peut
renvoyer au papier de travail qui la fonde. Elle se modifie tant qu'elle est proposée ; la
décision de l'entité (acceptée ou refusée, motif obligatoire en cas de refus) la fige.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models.revision import Adjustment, AdjustmentLine, AuditFile
from app.models.user import User
from app.models.workpaper import Workpaper
from app.revision.balances import clean_account
from app.revision.controls import plan_roots
from app.revision.currency import decimals, quantum
from app.revision.mapping import IFRS

router = APIRouter(tags=["Révision – ajustements"])
ZERO = Decimal(0)
MONEY = {"ge": 0, "max_digits": 20, "decimal_places": 2}


class LineIn(BaseModel):
    compte: str = Field(min_length=1, max_length=30)
    libelle: str | None = Field(default=None, max_length=300)
    debit: Decimal = Field(default=ZERO, **MONEY)
    credit: Decimal = Field(default=ZERO, **MONEY)


class AdjustmentIn(BaseModel):
    type: str = Field(pattern="^(correction|reclassement|retraitement_ifrs)$")
    libelle: str = Field(min_length=3, max_length=300)
    justification: str = Field(min_length=10, max_length=5000)
    workpaper_id: uuid.UUID | None = None
    lignes: list[LineIn] = Field(min_length=2, max_length=200)
    norme: str | None = Field(default=None, max_length=30)
    date_ecriture: dt.date | None = None

    @model_validator(mode="after")
    def _ifrs(self) -> "AdjustmentIn":
        if self.type == IFRS and not (self.norme and self.date_ecriture):
            raise ValueError("Un retraitement IFRS est daté et rattaché à une norme")
        return self


class DecisionIn(BaseModel):
    statut: str = Field(pattern="^(acceptee|refusee)$")
    motif: str | None = Field(default=None, max_length=5000)


def result_effect(lines: list[AdjustmentLine]) -> Decimal:
    """Effet sur le résultat : crédit − débit des comptes de gestion."""
    classes = get_settings().classes_resultat
    return sum((ln.credit - ln.debit for ln in lines if ln.compte[0] in classes), ZERO)


def lines_of(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[AdjustmentLine]]:
    out: dict[uuid.UUID, list[AdjustmentLine]] = {i: [] for i in ids}
    if ids:
        for ln in db.scalars(
            select(AdjustmentLine)
            .where(AdjustmentLine.adjustment_id.in_(ids))
            .order_by(AdjustmentLine.debit.desc(), AdjustmentLine.compte)
        ):
            out[ln.adjustment_id].append(ln)
    return out


def adjustment_out(adj: Adjustment, lines: list[AdjustmentLine], db: Session) -> dict[str, Any]:
    decider = db.get(User, adj.decision_par) if adj.decision_par else None
    return {
        "id": str(adj.id), "numero": adj.numero, "type": adj.type, "libelle": adj.libelle,
        "norme": adj.norme,
        "date_ecriture": adj.date_ecriture.isoformat() if adj.date_ecriture else None,
        "justification": adj.justification,
        "workpaper_id": str(adj.workpaper_id) if adj.workpaper_id else None,
        "statut": adj.statut, "motif_decision": adj.motif_decision,
        "decision_le": adj.decision_le.isoformat() if adj.decision_le else None,
        "decision_par": decider.nom if decider else None,
        "lignes": [{"compte": ln.compte, "libelle": ln.libelle, "debit": str(ln.debit),
                    "credit": str(ln.credit)} for ln in lines],
        "total": str(sum((ln.debit for ln in lines), ZERO)),
        "effet_resultat": str(result_effect(lines).quantize(Decimal("0.01"))),
    }  # fmt: skip


def file_adjustments(db: Session, file_id: uuid.UUID, ifrs: bool = False) -> list[Adjustment]:
    """Écritures d'ajustement du dossier ; avec `ifrs`, les retraitements IFRS (IFR-01)."""
    kind = (Adjustment.type == IFRS) if ifrs else (Adjustment.type != IFRS)
    return list(
        db.scalars(
            select(Adjustment)
            .where(Adjustment.audit_file_id == file_id, Adjustment.deleted_at.is_(None), kind)
            .order_by(Adjustment.numero)
        )
    )


def _get(db: Session, adjustment_id: uuid.UUID, user: User) -> tuple[Adjustment, AuditFile]:
    adj = db.get(Adjustment, adjustment_id)
    if adj is None or adj.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Écriture d'ajustement introuvable")
    file, engagement = get_file(db, adj.audit_file_id, user)
    require_work(file, engagement, user)
    return adj, file


def _check(db: Session, file: AuditFile, body: AdjustmentIn) -> list[LineIn]:
    if body.workpaper_id is not None:
        wp = db.get(Workpaper, body.workpaper_id)
        if wp is None or wp.deleted_at or wp.engagement_id != file.engagement_id:
            raise HTTPException(422, "Papier de travail inconnu dans la mission")
    places = decimals(db, file.devise)
    q = quantum(places)
    roots = plan_roots(db, file.framework_id)
    lines = []
    for ln in body.lignes:
        compte = clean_account(ln.compte)
        if (ln.debit > 0) == (ln.credit > 0):
            raise HTTPException(422, f"Compte {compte} : un montant au débit ou au crédit")
        if ln.debit != ln.debit.quantize(q) or ln.credit != ln.credit.quantize(q):
            raise HTTPException(422, f"Montants en {file.devise} : {places} décimale(s) au plus")
        if not any(compte.startswith(r) for r in roots):
            raise HTTPException(422, f"Compte {compte} hors plan")
        lines.append(ln.model_copy(update={"compte": compte}))
    debit = sum((ln.debit for ln in lines), ZERO)
    credit = sum((ln.credit for ln in lines), ZERO)
    if debit != credit:
        raise HTTPException(422, f"Écriture déséquilibrée : débit {debit} ≠ crédit {credit}")
    return lines


def _write_lines(db: Session, adj: Adjustment, lines: list[LineIn]) -> None:
    for old in lines_of(db, [adj.id])[adj.id]:
        db.delete(old)
    for ln in lines:
        db.add(AdjustmentLine(adjustment_id=adj.id, **ln.model_dump()))


@router.get("/audit-files/{file_id}/adjustments")
def list_adjustments(
    file_id: uuid.UUID, user: CurrentUser, db: DbSession, ifrs: bool = False
) -> list[dict[str, Any]]:
    file, _ = get_file(db, file_id, user)
    items = file_adjustments(db, file.id, ifrs)
    lines = lines_of(db, [a.id for a in items])
    return [adjustment_out(a, lines[a.id], db) for a in items]


@router.post("/audit-files/{file_id}/adjustments", status_code=status.HTTP_201_CREATED)
def create_adjustment(
    file_id: uuid.UUID, body: AdjustmentIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    lines = _check(db, file, body)
    last = db.scalar(select(func.max(Adjustment.numero)).where(Adjustment.audit_file_id == file.id))
    adj = Adjustment(
        engagement_id=file.engagement_id, audit_file_id=file.id, numero=(last or 0) + 1,
        **body.model_dump(exclude={"lignes"}),
    )  # fmt: skip
    db.add(adj)
    db.flush()
    _write_lines(db, adj, lines)
    db.commit()
    return adjustment_out(adj, lines_of(db, [adj.id])[adj.id], db)


@router.put("/adjustments/{adjustment_id}")
def update_adjustment(
    adjustment_id: uuid.UUID, body: AdjustmentIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    adj, file = _get(db, adjustment_id, user)
    if adj.statut != "proposee":
        raise HTTPException(status.HTTP_409_CONFLICT, "Écriture déjà décidée : non modifiable")
    lines = _check(db, file, body)
    for key, value in body.model_dump(exclude={"lignes"}).items():
        setattr(adj, key, value)
    _write_lines(db, adj, lines)
    db.commit()
    return adjustment_out(adj, lines_of(db, [adj.id])[adj.id], db)


@router.post("/adjustments/{adjustment_id}/decision")
def decide(
    adjustment_id: uuid.UUID, body: DecisionIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Décision de l'entité, enregistrée par l'équipe d'audit."""
    adj, _ = _get(db, adjustment_id, user)
    if adj.statut != "proposee":
        raise HTTPException(status.HTTP_409_CONFLICT, "Écriture déjà décidée")
    if body.statut == "refusee" and not (body.motif or "").strip():
        raise HTTPException(422, "Motif du refus obligatoire")
    adj.statut, adj.motif_decision = body.statut, body.motif
    adj.decision_le, adj.decision_par = dt.datetime.now(dt.UTC), user.id
    db.commit()
    return adjustment_out(adj, lines_of(db, [adj.id])[adj.id], db)


@router.delete("/adjustments/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_adjustment(adjustment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    adj, _ = _get(db, adjustment_id, user)
    if adj.statut != "proposee":
        raise HTTPException(status.HTTP_409_CONFLICT, "Écriture déjà décidée : conservée")
    adj.deleted_at, adj.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


# --- Anomalies non corrigées (REV-22) -----------------------------------------------------------


@router.get("/audit-files/{file_id}/unadjusted")
def unadjusted(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Tableau des anomalies non corrigées (ISA 450) : écritures proposées ou refusées.

    Les anomalies inférieures au seuil d'insignifiance sont listées mais non cumulées ; le
    cumul des effets sur le résultat est comparé au seuil de planification et au seuil de
    signification ; les reclassements sont cumulés à part (présentation).
    """
    file, _ = get_file(db, file_id, user)
    if file.seuil_signification is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Fixez d'abord le seuil de signification")
    items = [a for a in file_adjustments(db, file.id) if a.statut != "acceptee"]
    lines = lines_of(db, [a.id for a in items])
    rows, total_result, total_reclass = [], ZERO, ZERO
    for a in items:
        effect = result_effect(lines[a.id])
        amount = sum((ln.debit for ln in lines[a.id]), ZERO)
        weight = abs(effect) if a.type == "correction" else amount
        trivial = weight <= file.seuil_insignifiant
        if not trivial:
            if a.type == "correction":
                total_result += effect
            else:
                total_reclass += amount
        rows.append({
            "numero": a.numero, "libelle": a.libelle, "type": a.type, "statut": a.statut,
            "effet_resultat": str(effect.quantize(Decimal("0.01"))), "montant": str(amount),
            "insignifiant": trivial,
            "individuellement_significatif": weight >= file.seuil_signification,
        })  # fmt: skip
    cumul = abs(total_result)
    if cumul >= file.seuil_signification or any(r["individuellement_significatif"] for r in rows):
        conclusion = "significatif"
    elif cumul >= file.seuil_planification:
        conclusion = "vigilance"
    else:
        conclusion = "non_significatif"
    return {
        "seuils": {"signification": str(file.seuil_signification),
                   "planification": str(file.seuil_planification),
                   "insignifiant": str(file.seuil_insignifiant)},
        "anomalies": rows,
        "cumul_resultat": str(total_result.quantize(Decimal("0.01"))),
        "cumul_reclassements": str(total_reclass),
        "conclusion": conclusion,
    }  # fmt: skip
