"""Matrice des risques par cycle et par assertion (REV-14), qui alimente le programme de
travail de la mission (Module 1, AUD-10 et AUD-11).

Pour chaque cycle, le montant N (somme des soldes absolus de ses comptes) est rapproché du
seuil de signification. Chaque cellule reçoit un risque inhérent et un risque lié au contrôle
(faible, moyen, élevé), éventuellement qualifié de risque important ; leur combinaison donne
le risque d'anomalie significative. La génération du programme crée, pour chaque cellule à
risque moyen ou élevé, un risque, un contrôle et des procédures dans la matrice de la mission.
"""

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.program import add_procedure, editable
from app.models.program import Control, ControlNature, ControlType, Frequency, Risk, RiskControl
from app.models.revision import AccountingFramework, AssertionRisk, AuditFile
from app.revision.cycles import assertions, combined, cycle_of, cycles_for, library
from app.revision.mapping import assignments

router = APIRouter(tags=["Révision – matrice des risques"])
LEVEL = "^(faible|moyen|eleve)$"


class CellIn(BaseModel):
    risque_inherent: str | None = Field(default=None, pattern=LEVEL)
    risque_controle: str | None = Field(default=None, pattern=LEVEL)
    risque_important: bool = False
    commentaire: str | None = Field(default=None, max_length=5000)


def _cycles(db: Session, file: AuditFile) -> list[dict[str, Any]]:
    return cycles_for(db.get(AccountingFramework, file.framework_id).code)


def _cells(db: Session, file_id: uuid.UUID) -> dict[tuple[str, str], AssertionRisk]:
    rows = db.scalars(
        select(AssertionRisk).where(
            AssertionRisk.audit_file_id == file_id, AssertionRisk.deleted_at.is_(None)
        )
    )
    return {(c.cycle, c.assertion): c for c in rows}


def _matrix(db: Session, file: AuditFile) -> dict[str, Any]:
    cycles = _cycles(db, file)
    amounts: dict[str, Decimal] = defaultdict(Decimal)
    for a in assignments(db, file):
        code = cycle_of(a.compte, cycles)
        if code is not None and "N" in a.soldes:
            amounts[code] += abs(a.soldes["N"])
    cells = _cells(db, file.id)
    out_cells = []
    for c in cells.values():
        level = combined(c.risque_inherent, c.risque_controle, c.risque_important)
        out_cells.append({
            "cycle": c.cycle, "assertion": c.assertion, "risque_inherent": c.risque_inherent,
            "risque_controle": c.risque_controle, "risque_important": c.risque_important,
            "commentaire": c.commentaire, "risque": level,
            "dans_programme": c.risk_id is not None,
        })  # fmt: skip
    threshold = file.seuil_signification
    return {
        "cycles": [
            {
                "code": c["code"],
                "libelle": c["libelle"],
                "racines": c["racines"],
                "montant_n": str(amounts.get(c["code"], Decimal(0))),
                "significatif": None
                if threshold is None
                else amounts.get(c["code"], 0) > threshold,
            }
            for c in cycles
        ],  # fmt: skip
        "assertions": [{"code": a["code"], "libelle": a["libelle"]} for a in assertions()],
        "niveaux": library()["niveaux"],
        "cellules": out_cells,
    }


@router.get("/audit-files/{file_id}/risk-matrix")
def read_matrix(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return _matrix(db, file)


@router.put("/audit-files/{file_id}/risk-matrix/{cycle}/{assertion}")
def set_cell(
    file_id: uuid.UUID, cycle: str, assertion: str, body: CellIn, user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:  # fmt: skip
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    if cycle not in {c["code"] for c in _cycles(db, file)} or assertion not in {
        a["code"] for a in assertions()
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle ou assertion inconnu")
    cell = _cells(db, file.id).get((cycle, assertion))
    if cell is None:
        cell = AssertionRisk(engagement_id=file.engagement_id, audit_file_id=file.id,
                             cycle=cycle, assertion=assertion)  # fmt: skip
        db.add(cell)
    for key, value in body.model_dump().items():
        setattr(cell, key, value)
    db.commit()
    return _matrix(db, file)


@router.post("/audit-files/{file_id}/risk-matrix/program")
def generate_program(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Alimente la matrice risques / contrôles / procédures de la mission (Module 1)."""
    file, _ = get_file(db, file_id, user)
    engagement = editable(db, file.engagement_id, user)  # chef de mission, mission ouverte
    lib = library()
    cycles = {c["code"]: c for c in _cycles(db, file)}
    names = {a["code"]: a for a in assertions()}
    created = updated = 0
    for cell in _cells(db, file.id).values():
        level = combined(cell.risque_inherent, cell.risque_controle, cell.risque_important)
        if level not in ("moyen", "eleve"):
            continue
        cycle, assertion = cycles[cell.cycle], names[cell.assertion]
        shown = "élevé" if level == "eleve" else level
        label = f"{cycle['libelle']} – {assertion['libelle']} : risque {shown}"
        if cell.risque_important:
            label += " (risque important)"
        risk = db.get(Risk, cell.risk_id) if cell.risk_id else None
        if risk is not None and risk.deleted_at is None:
            risk.libelle, risk.description = label, cell.commentaire
            updated += 1
            continue
        risk = Risk(
            libelle=label, description=cell.commentaire, cycle=cycle["cycle_mission"],
            categorie="reporting", bibliotheque=False, engagement_id=engagement.id,
        )  # fmt: skip
        control = Control(
            libelle=f"Contrôles clés – {cycle['libelle']} ({assertion['libelle'].lower()})",
            cycle=cycle["cycle_mission"], type_controle=ControlType.DETECTIF.value,
            nature=ControlNature.MANUEL.value, frequence=Frequency.PONCTUEL.value,
            bibliotheque=False, engagement_id=engagement.id,
        )  # fmt: skip
        db.add_all([risk, control])
        db.flush()
        db.add(RiskControl(risk_id=risk.id, control_id=control.id))
        fmt = {"cycle": cycle["libelle"].lower(), "assertion": assertion["libelle"].lower()}
        add_procedure(db, engagement, control, assertion["procedure"].format(**fmt), "substantif")
        if level == "eleve":
            add_procedure(db, engagement, control, lib["procedure_etendue"].format(**fmt),
                          "substantif")  # fmt: skip
        if cell.risque_controle == "faible":
            add_procedure(db, engagement, control, lib["procedure_controles"].format(**fmt),
                          "efficacite")  # fmt: skip
        cell.risk_id = risk.id
        created += 1
    db.commit()
    return {"crees": created, "mis_a_jour": updated, **_matrix(db, file)}
