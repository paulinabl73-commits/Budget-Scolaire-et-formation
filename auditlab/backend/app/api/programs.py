"""Programmes de travail types par cycle (REV-16) : bibliothèque adaptable par référentiel et
application au programme de la mission (Module 1)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession, require
from app.api.program import add_procedure, editable
from app.api.risk_matrix import file_cycles
from app.models.program import (
    Control,
    ControlNature,
    ControlType,
    Frequency,
    Procedure,
    Risk,
    RiskControl,
)
from app.models.revision import AccountingFramework, ProgramStep
from app.models.user import User
from app.revision import programs
from app.revision.cycles import assertions, cycles_for
from app.security.roles import Perm

router = APIRouter(tags=["Révision – programmes types"])
Reader = Annotated[User, Depends(require(Perm.REVISION_READ, Perm.FRAMEWORKS_MANAGE))]
Manager = Annotated[User, Depends(require(Perm.FRAMEWORKS_MANAGE))]
ASSERTION = "^(existence|exhaustivite|evaluation|droits_obligations|separation|presentation)$"
TEST = "^(conception|efficacite|substantif)$"


class StepIn(BaseModel):
    referentiel: str = Field(min_length=2, max_length=20)
    cycle: str = Field(min_length=2, max_length=40)
    assertion: str = Field(pattern=ASSERTION)
    type_test: str = Field(default="substantif", pattern=TEST)
    description: str = Field(min_length=10, max_length=5000)


class StepUpdate(BaseModel):
    assertion: str | None = Field(default=None, pattern=ASSERTION)
    type_test: str | None = Field(default=None, pattern=TEST)
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    ordre: int | None = Field(default=None, ge=0)
    actif: bool | None = None


def step_out(s: ProgramStep) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "referentiel": s.referentiel,
        "cycle": s.cycle,
        "assertion": s.assertion,
        "type_test": s.type_test,
        "description": s.description,
        "ordre": s.ordre,
        "actif": s.actif,
    }


@router.get("/revision-programs")
def list_steps(user: Reader, db: DbSession, referentiel: str = "SYSCOHADA") -> dict[str, Any]:
    cycles = cycles_for(referentiel)
    items = programs.steps(db, referentiel, active_only=False)
    return {
        "referentiel": programs.referentiel_for(db, referentiel),
        "cycles": [{"code": c["code"], "libelle": c["libelle"]} for c in cycles],
        "assertions": [{"code": a["code"], "libelle": a["libelle"]} for a in assertions()],
        "procedures": [step_out(s) for s in items],
    }


@router.post("/revision-programs", status_code=status.HTTP_201_CREATED)
def create_step(body: StepIn, user: Manager, db: DbSession) -> dict[str, Any]:
    if body.cycle not in {c["code"] for c in cycles_for(body.referentiel)}:
        raise HTTPException(422, "Cycle inconnu pour ce référentiel")
    last = db.scalar(
        select(func.max(ProgramStep.ordre)).where(
            ProgramStep.referentiel == body.referentiel, ProgramStep.cycle == body.cycle
        )
    )
    step = ProgramStep(**body.model_dump(), ordre=(last or 0) + 1)
    db.add(step)
    db.commit()
    return step_out(step)


@router.patch("/revision-programs/{step_id}")
def update_step(
    step_id: uuid.UUID, body: StepUpdate, user: Manager, db: DbSession
) -> dict[str, Any]:
    step = db.get(ProgramStep, step_id)
    if step is None or step.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procédure type introuvable")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(step, key, value)
    db.commit()
    return step_out(step)


@router.post("/audit-files/{file_id}/programs/{cycle}/apply")
def apply_program(
    file_id: uuid.UUID, cycle: str, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Reprend le programme type du cycle dans la matrice de la mission ; sans doublon."""
    file, _ = get_file(db, file_id, user)
    engagement = editable(db, file.engagement_id, user)
    known = {c["code"]: c for c in file_cycles(db, file)}
    if cycle not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle inconnu")
    code = db.get(AccountingFramework, file.framework_id).code
    items = programs.steps(db, code, cycle)
    label = f"{known[cycle]['libelle']} – programme de révision type"
    risk = db.scalar(
        select(Risk).where(
            Risk.engagement_id == engagement.id, Risk.libelle == label, Risk.deleted_at.is_(None)
        )
    )
    if risk is None:
        risk = Risk(
            libelle=label,
            cycle=known[cycle]["cycle_mission"],
            categorie="reporting",
            bibliotheque=False,
            engagement_id=engagement.id,
        )
        control = Control(
            libelle=f"Programme de travail type – {known[cycle]['libelle']}",
            cycle=known[cycle]["cycle_mission"],
            type_controle=ControlType.DETECTIF.value,
            nature=ControlNature.MANUEL.value,
            frequence=Frequency.PONCTUEL.value,
            bibliotheque=False,
            engagement_id=engagement.id,
        )
        db.add_all([risk, control])
        db.flush()
        db.add(RiskControl(risk_id=risk.id, control_id=control.id))
    else:
        control = db.scalar(
            select(Control)
            .join(RiskControl, RiskControl.control_id == Control.id)
            .where(RiskControl.risk_id == risk.id, Control.deleted_at.is_(None))
        )
    names = {a["code"]: a["libelle"] for a in assertions()}
    existing = set(
        db.scalars(
            select(Procedure.description).where(
                Procedure.control_id == control.id, Procedure.deleted_at.is_(None)
            )
        )
    )
    added = 0
    for step in items:
        text = f"[{names[step.assertion]}] {step.description}"
        if text not in existing:
            add_procedure(db, engagement, control, text, step.type_test)
            added += 1
    db.commit()
    return {"cycle": cycle, "procedures_ajoutees": added, "procedures_programme": len(items)}
