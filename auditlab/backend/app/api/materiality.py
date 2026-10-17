"""Seuil de signification (REV-11) : base au choix parmi celles du référentiel, pourcentage
saisi, seuil de planification et seuil des anomalies manifestement insignifiantes dérivés.

La fourchette indicative de chaque base est une donnée du référentiel (pct_min, pct_max) ; un
pourcentage hors fourchette est admis mais signalé. Le montant de la base est calculé sur les
états N ; un montant saisi (budget, données réestimées) est admis, toujours justifié.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_direct
from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models.revision import AccountingFramework, AuditFile
from app.revision.currency import decimals, quantum
from app.revision.formula import evaluate
from app.revision.mapping import UnmappedError, file_values

router = APIRouter(tags=["Révision – planification"])
PCT = {"gt": 0, "le": 100, "max_digits": 7, "decimal_places": 4}


class MaterialityIn(BaseModel):
    base_seuil: str = Field(min_length=1, max_length=40)
    pct_seuil: Decimal = Field(**PCT)
    montant_base: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=2)
    pct_planification: Decimal | None = Field(default=None, **PCT)
    pct_insignifiant: Decimal | None = Field(default=None, **PCT)
    seuil_variation_pct: Decimal | None = Field(default=None, **PCT)
    justification: str = Field(min_length=10, max_length=5000)

    @model_validator(mode="after")
    def _order(self) -> "MaterialityIn":
        settings = get_settings()
        plan = self.pct_planification or Decimal(str(settings.pct_planification_defaut))
        trivial = self.pct_insignifiant or Decimal(str(settings.pct_insignifiant_defaut))
        if trivial >= plan:
            raise ValueError(
                "Le seuil d'insignifiance doit être inférieur au seuil de planification"
            )
        return self


def _bases(db: Session, file: AuditFile) -> tuple[list[dict[str, Any]], str | None]:
    fw = db.get(AccountingFramework, file.framework_id)
    try:
        values: dict[str, Decimal] | None = file_values(db, file)["N"]
        message = None
    except UnmappedError as exc:
        values, message = None, str(exc)
    out = []
    for b in fw.bases_seuil:
        amount = evaluate(b["formule"], values) if values is not None else None
        out.append({
            "code": b["code"], "libelle": b["libelle"],
            "pct_min": b.get("pct_min"), "pct_max": b.get("pct_max"),
            "montant": str(amount) if amount is not None else None,
        })  # fmt: skip
    return out, message


def _state(db: Session, file: AuditFile) -> dict[str, Any]:
    settings = get_settings()
    bases, message = _bases(db, file)
    fields = ("base_seuil", "montant_base", "pct_seuil", "seuil_signification",
              "pct_planification", "seuil_planification", "pct_insignifiant",
              "seuil_insignifiant", "justification_seuil", "seuil_variation_pct")  # fmt: skip
    current = {k: getattr(file, k) for k in fields}
    return {
        "bases": bases,
        "etats_indisponibles": message,
        "defauts": {
            "pct_planification": str(settings.pct_planification_defaut),
            "pct_insignifiant": str(settings.pct_insignifiant_defaut),
        },
        "seuil": {k: str(v) if isinstance(v, Decimal) else v for k, v in current.items()},
    }


@router.get("/audit-files/{file_id}/materiality")
def read_materiality(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return _state(db, file)


@router.put("/audit-files/{file_id}/materiality")
def set_materiality(
    file_id: uuid.UUID, body: MaterialityIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_direct(file, engagement, user)
    bases, message = _bases(db, file)
    base = next((b for b in bases if b["code"] == body.base_seuil), None)
    if base is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Base de seuil inconnue")
    amount = body.montant_base
    if amount is None:
        if base["montant"] is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"{message} : saisissez le montant de la base"
            )
        amount = Decimal(base["montant"])
    if amount <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Base négative ou nulle (ex. perte) : retenez une autre base ou saisissez un montant",
        )
    settings = get_settings()
    q = quantum(decimals(db, file.devise))
    pct_plan = body.pct_planification or Decimal(str(settings.pct_planification_defaut))
    pct_trivial = body.pct_insignifiant or Decimal(str(settings.pct_insignifiant_defaut))
    seuil = (amount * body.pct_seuil / 100).quantize(q, ROUND_HALF_UP)
    file.base_seuil = body.base_seuil
    file.montant_base = amount
    file.pct_seuil = body.pct_seuil
    file.seuil_signification = seuil
    file.pct_planification = pct_plan
    file.seuil_planification = (seuil * pct_plan / 100).quantize(q, ROUND_HALF_UP)
    file.pct_insignifiant = pct_trivial
    file.seuil_insignifiant = (seuil * pct_trivial / 100).quantize(q, ROUND_HALF_UP)
    file.justification_seuil = body.justification
    if body.seuil_variation_pct is not None:
        file.seuil_variation_pct = body.seuil_variation_pct
    db.commit()
    db.refresh(file)
    state = _state(db, file)
    warnings = []
    low, high = base.get("pct_min"), base.get("pct_max")
    if low is not None and high is not None and not Decimal(low) <= body.pct_seuil <= Decimal(high):
        warnings.append(f"Pourcentage hors de la fourchette indicative ({low} % à {high} %)")
    if body.montant_base is not None and base["montant"] is not None:
        if Decimal(base["montant"]) != body.montant_base:
            warnings.append("Montant de base saisi, différent du montant calculé sur les états N")
    state["avertissements"] = warnings
    return state
