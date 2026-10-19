"""Tableau de passage du résultat comptable au résultat fiscal (RCO-20).

Résultat comptable avant impôt = résultat net révisé + impôt sur le résultat comptabilisé.
Réintégrations et déductions : règles du pays (montant = solde des comptes désignés ×
pourcentage), montant retenu à la place du montant calculé, lignes saisies. Impôt sur les
sociétés = résultat fiscal positif × taux ; impôt minimum = chiffre d'affaires × taux, borné
par le plancher et le plafond (0 = sans plafond) ; impôt dû = le plus élevé des deux. Taux et
bornes : paramètres fiscaux du pays (RCO-22)."""

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.api.tax_review import accounts_of
from app.cabinet.fiscal import values
from app.config import get_settings
from app.models.portfolio import FiscalAdjustmentRule, TaxBridgeLine
from app.models.revision import AuditFile
from app.revision.currency import decimals, quantum
from app.revision.mapping import assignments
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)


class RuleIn(BaseModel):
    pays: str = Field(min_length=2, max_length=40)
    code: str = Field(min_length=2, max_length=40)
    libelle: str = Field(min_length=2, max_length=300)
    sens: Literal["reintegration", "deduction"]
    racines: list[str] = Field(default=[], max_length=50)
    pourcentage: Decimal = Field(default=Decimal(100), ge=0, le=100)
    exercice: int | None = Field(default=None, ge=1990, le=2100)


class LineIn(BaseModel):
    rule_code: str | None = Field(default=None, max_length=40)
    libelle: str = Field(min_length=2, max_length=300)
    sens: Literal["reintegration", "deduction"]
    montant: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    commentaire: str | None = Field(default=None, max_length=2000)


def _rules(db: Session, pays: str, exercice: int) -> list[FiscalAdjustmentRule]:
    rows = db.scalars(
        select(FiscalAdjustmentRule)
        .where(
            FiscalAdjustmentRule.pays == pays,
            FiscalAdjustmentRule.actif.is_(True),
            FiscalAdjustmentRule.deleted_at.is_(None),
        )
        .order_by(FiscalAdjustmentRule.code)
    )
    return [r for r in rows if r.exercice is None or r.exercice <= exercice]


def bridge(db: Session, file: AuditFile) -> dict[str, Any]:
    q = quantum(decimals(db, file.devise))
    classes = get_settings().classes_resultat
    books = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file, adjusted=True)}

    def credit_of(prefixes: list[str]) -> Decimal:
        return -sum((v for c, v in books.items() if any(c.startswith(p) for p in prefixes)), ZERO)

    acc = accounts_of(db, file)
    net = -sum((v for c, v in books.items() if c[0] in classes), ZERO)
    tax_booked = -credit_of(acc.get("impot_resultat", []))
    before_tax = net + tax_booked
    lines = list(
        db.scalars(
            select(TaxBridgeLine).where(
                TaxBridgeLine.audit_file_id == file.id, TaxBridgeLine.deleted_at.is_(None)
            )
        )
    )
    overrides = {ln.rule_code: ln for ln in lines if ln.rule_code}
    items = []
    for r in _rules(db, file.pays or "", file.exercice):
        balance = -credit_of(r.racines)  # solde débiteur des charges désignées
        computed = (abs(balance) * r.pourcentage / 100).quantize(q, ROUND_HALF_UP)
        kept = overrides.get(r.code)
        items.append(
            {
                "code": r.code,
                "libelle": r.libelle,
                "sens": r.sens,
                "calcule": str(computed),
                "montant": str(kept.montant if kept else computed),
                "origine": "saisi" if kept else "regle",
                "commentaire": kept.commentaire if kept else None,
                "id": str(kept.id) if kept else None,
            }
        )
    for ln in lines:
        if not ln.rule_code:
            items.append(
                {
                    "code": None,
                    "libelle": ln.libelle,
                    "sens": ln.sens,
                    "calcule": None,
                    "montant": str(ln.montant),
                    "origine": "ligne",
                    "commentaire": ln.commentaire,
                    "id": str(ln.id),
                }
            )
    plus = sum((Decimal(i["montant"]) for i in items if i["sens"] == "reintegration"), ZERO)
    minus = sum((Decimal(i["montant"]) for i in items if i["sens"] == "deduction"), ZERO)
    fiscal = before_tax + plus - minus
    turnover = credit_of(acc.get("chiffre_affaires", []))
    out: dict[str, Any] = {
        "resultat_net": str(net),
        "impot_comptabilise": str(tax_booked),
        "resultat_avant_impot": str(before_tax),
        "elements": items,
        "reintegrations": str(plus),
        "deductions": str(minus),
        "resultat_fiscal": str(fiscal),
        "chiffre_affaires": str(turnover),
    }
    try:
        p = values(
            db,
            file.pays or "",
            file.exercice,
            ["taux_is", "taux_impot_minimum", "impot_minimum_plancher", "impot_minimum_plafond"],
        )
    except HTTPException as exc:
        return {**out, "impot": None, "parametres_manquants": exc.detail["points"]}
    corporate = (max(fiscal, ZERO) * p["taux_is"] / 100).quantize(q, ROUND_HALF_UP)
    minimum = max(turnover * p["taux_impot_minimum"] / 100, p["impot_minimum_plancher"])
    if p["impot_minimum_plafond"] > 0:
        minimum = min(minimum, p["impot_minimum_plafond"])
    minimum = minimum.quantize(q, ROUND_HALF_UP)
    due = max(corporate, minimum)
    return {
        **out,
        "parametres_manquants": [],
        "impot": {
            "impot_societes": str(corporate),
            "impot_minimum": str(minimum),
            "impot_du": str(due),
            "regime": "impot_minimum" if minimum > corporate else "impot_societes",
            "ecart_comptabilise": str(due - tax_booked),
        },
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> AuditFile:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    _client(db, file)
    return file


@router.get("/fiscal-rules")
def list_rules(user: CurrentUser, db: DbSession, pays: str | None = None) -> list[dict[str, Any]]:
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    query = select(FiscalAdjustmentRule).where(FiscalAdjustmentRule.deleted_at.is_(None))
    if pays:
        query = query.where(FiscalAdjustmentRule.pays == pays)
    return [
        {
            "id": str(r.id),
            "pays": r.pays,
            "code": r.code,
            "libelle": r.libelle,
            "sens": r.sens,
            "racines": r.racines,
            "pourcentage": str(r.pourcentage),
            "exercice": r.exercice,
        }
        for r in db.scalars(query.order_by(FiscalAdjustmentRule.pays, FiscalAdjustmentRule.code))
    ]


@router.post("/fiscal-rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if not has_permission(user.role, Perm.PORTFOLIO_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux experts-comptables")
    if any(not r.isdigit() for r in body.racines):
        raise HTTPException(422, "Racines de comptes numériques attendues")
    rule = FiscalAdjustmentRule(**body.model_dump())
    db.add(rule)
    db.commit()
    return {"id": str(rule.id), "code": rule.code}


@router.delete("/fiscal-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    if not has_permission(user.role, Perm.PORTFOLIO_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux experts-comptables")
    rule = db.get(FiscalAdjustmentRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Règle introuvable")
    rule.deleted_at, rule.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.get("/audit-files/{file_id}/tax-bridge")
def read_bridge(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return bridge(db, _context(db, file_id, user, False))


@router.post("/audit-files/{file_id}/tax-bridge/lines", status_code=status.HTTP_201_CREATED)
def add_line(file_id: uuid.UUID, body: LineIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Ligne saisie, ou montant retenu à la place du montant calculé d'une règle."""
    file = _context(db, file_id, user, True)
    if body.rule_code:
        rule = next(
            (r for r in _rules(db, file.pays or "", file.exercice) if r.code == body.rule_code),
            None,
        )
        if rule is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Règle inconnue pour ce pays")
        for old in db.scalars(
            select(TaxBridgeLine).where(
                TaxBridgeLine.audit_file_id == file.id,
                TaxBridgeLine.rule_code == body.rule_code,
                TaxBridgeLine.deleted_at.is_(None),
            )
        ):
            old.deleted_at, old.deleted_by = dt.datetime.now(dt.UTC), user.id
        body = body.model_copy(update={"sens": rule.sens})
    db.add(TaxBridgeLine(audit_file_id=file.id, **body.model_dump()))
    db.commit()
    return bridge(db, file)


@router.delete("/audit-files/{file_id}/tax-bridge/lines/{line_id}", status_code=204)
def delete_line(file_id: uuid.UUID, line_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    file = _context(db, file_id, user, True)
    line = db.get(TaxBridgeLine, line_id)
    if line is None or line.deleted_at is not None or line.audit_file_id != file.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ligne introuvable")
    line.deleted_at, line.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()
