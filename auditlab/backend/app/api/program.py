"""Matrice risques/contrôles de la mission et procédures de test (AUD-11)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.library import (
    control_out,
    linked_controls,
    procedures_by_control,
    risk_out,
    set_links,
)
from app.api.mission_access import (
    can_manage,
    ensure_open,
    get_engagement,
    require_manager,
    visible_engagements,
)
from app.models.engagement import Engagement, MissionRole
from app.models.program import Control, Procedure, ProcedureStatus, Risk, RiskControl
from app.models.user import User
from app.schemas_mission import (
    AssignmentIn,
    ControlOut,
    ControlUpdate,
    LinkIn,
    MatrixOut,
    MissionControlIn,
    MissionRiskIn,
    MyProcedureOut,
    ProcedureIn,
    ProcedureOut,
    ProcedureStatusIn,
    ProcedureUpdate,
    RiskOut,
    RiskUpdate,
)

router = APIRouter(prefix="/engagements", tags=["Programme de travail"])

RISK_FIELDS = ("libelle", "description", "cycle", "categorie")
CONTROL_FIELDS = ("libelle", "description", "cycle", "type_controle", "nature", "frequence")


def editable(db: Session, engagement_id: uuid.UUID, user: User) -> Engagement:
    engagement = get_engagement(db, engagement_id, user)
    require_manager(engagement, user)
    ensure_open(engagement)
    return engagement


def mission_risks(db: Session, engagement: Engagement) -> list[Risk]:
    return list(
        db.scalars(
            select(Risk)
            .where(Risk.engagement_id == engagement.id, Risk.deleted_at.is_(None))
            .order_by(Risk.cycle, Risk.created_at)
        )
    )


def mission_controls(db: Session, engagement: Engagement) -> list[Control]:
    return list(
        db.scalars(
            select(Control)
            .where(Control.engagement_id == engagement.id, Control.deleted_at.is_(None))
            .order_by(Control.cycle, Control.created_at)
        )
    )


def matrix(db: Session, engagement: Engagement) -> MatrixOut:
    risks = mission_risks(db, engagement)
    controls = mission_controls(db, engagement)
    links = linked_controls(db, [r.id for r in risks])
    procedures = procedures_by_control(db, [c.id for c in controls])
    return MatrixOut(
        risques=[risk_out(r, links[r.id], procedures) for r in risks],
        controles=[control_out(c, procedures[c.id]) for c in controls],
    )


def _next_procedure_ref(db: Session, engagement: Engagement) -> str:
    count = (
        db.scalar(
            select(func.count())
            .select_from(Procedure)
            .where(Procedure.engagement_id == engagement.id)
        )
        or 0
    )
    return f"P-{count + 1:02d}"


def copy_control(db: Session, engagement: Engagement, source: Control) -> Control:
    """Copie un contrôle de la bibliothèque (une seule fois par mission) et ses procédures."""
    existing = db.scalar(
        select(Control).where(
            Control.engagement_id == engagement.id,
            Control.source_id == source.id,
            Control.deleted_at.is_(None),
        )
    )
    if existing:
        return existing
    control = Control(
        **{f: getattr(source, f) for f in CONTROL_FIELDS},
        bibliotheque=False,
        engagement_id=engagement.id,
        source_id=source.id,
    )
    db.add(control)
    db.flush()
    for p in procedures_by_control(db, [source.id])[source.id]:
        add_procedure(db, engagement, control, p.description, p.type_test)
    return control


def add_procedure(
    db: Session, engagement: Engagement, control: Control, description: str, type_test: str
) -> Procedure:
    procedure = Procedure(
        control_id=control.id,
        engagement_id=engagement.id,
        reference=_next_procedure_ref(db, engagement),
        description=description,
        type_test=type_test,
        bibliotheque=False,
    )
    db.add(procedure)
    db.flush()
    return procedure


def copy_risk(db: Session, engagement: Engagement, source: Risk) -> Risk:
    risk = Risk(
        **{f: getattr(source, f) for f in RISK_FIELDS},
        bibliotheque=False,
        engagement_id=engagement.id,
        source_id=source.id,
    )
    db.add(risk)
    db.flush()
    controls = [
        copy_control(db, engagement, c) for c in linked_controls(db, [source.id])[source.id]
    ]
    set_links(db, risk, [c.id for c in controls])
    return risk


def _mission_risk(db: Session, engagement: Engagement, risk_id: uuid.UUID) -> Risk:
    risk = db.scalar(
        select(Risk).where(
            Risk.id == risk_id, Risk.engagement_id == engagement.id, Risk.deleted_at.is_(None)
        )
    )
    if risk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Risque introuvable dans la mission")
    return risk


def mission_control(db: Session, engagement: Engagement, control_id: uuid.UUID) -> Control:
    control = db.scalar(
        select(Control).where(
            Control.id == control_id,
            Control.engagement_id == engagement.id,
            Control.deleted_at.is_(None),
        )
    )
    if control is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrôle introuvable dans la mission")
    return control


def mission_procedure(db: Session, engagement: Engagement, procedure_id: uuid.UUID) -> Procedure:
    procedure = db.scalar(
        select(Procedure).where(
            Procedure.id == procedure_id,
            Procedure.engagement_id == engagement.id,
            Procedure.deleted_at.is_(None),
        )
    )
    if procedure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procédure introuvable dans la mission")
    return procedure


@router.get("/{engagement_id}/matrix", response_model=MatrixOut)
def read_matrix(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MatrixOut:
    return matrix(db, get_engagement(db, engagement_id, user))


@router.post("/{engagement_id}/risks", response_model=RiskOut, status_code=201)
def add_risk(
    engagement_id: uuid.UUID, body: MissionRiskIn, user: CurrentUser, db: DbSession
) -> RiskOut:
    engagement = editable(db, engagement_id, user)
    if body.library_risk_id:
        source = db.scalar(
            select(Risk).where(
                Risk.id == body.library_risk_id,
                Risk.bibliotheque.is_(True),
                Risk.deleted_at.is_(None),
            )
        )
        if source is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Risque introuvable dans la bibliothèque"
            )
        risk = copy_risk(db, engagement, source)
    else:
        values = body.model_dump(mode="json", include=set(RISK_FIELDS))
        if not all(values.get(f) for f in ("libelle", "cycle", "categorie")):
            raise HTTPException(422, "Libellé, cycle et catégorie sont obligatoires")
        risk = Risk(**values, bibliotheque=False, engagement_id=engagement.id)
        db.add(risk)
    db.commit()
    controls = linked_controls(db, [risk.id])[risk.id]
    return risk_out(risk, controls, procedures_by_control(db, [c.id for c in controls]))


@router.patch("/{engagement_id}/risks/{risk_id}", response_model=RiskOut)
def update_risk(
    engagement_id: uuid.UUID, risk_id: uuid.UUID, body: RiskUpdate, user: CurrentUser, db: DbSession
) -> RiskOut:
    engagement = editable(db, engagement_id, user)
    risk = _mission_risk(db, engagement, risk_id)
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        if value is not None or key == "description":
            setattr(risk, key, value)
    db.commit()
    controls = linked_controls(db, [risk.id])[risk.id]
    return risk_out(risk, controls, procedures_by_control(db, [c.id for c in controls]))


@router.put("/{engagement_id}/risks/{risk_id}/controls", response_model=RiskOut)
def link_controls(
    engagement_id: uuid.UUID, risk_id: uuid.UUID, body: LinkIn, user: CurrentUser, db: DbSession
) -> RiskOut:
    engagement = editable(db, engagement_id, user)
    risk = _mission_risk(db, engagement, risk_id)
    for control_id in body.control_ids:
        mission_control(db, engagement, control_id)
    set_links(db, risk, list(dict.fromkeys(body.control_ids)))
    db.commit()
    controls = linked_controls(db, [risk.id])[risk.id]
    return risk_out(risk, controls, procedures_by_control(db, [c.id for c in controls]))


@router.delete("/{engagement_id}/risks/{risk_id}", status_code=204)
def delete_risk(
    engagement_id: uuid.UUID, risk_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    engagement = editable(db, engagement_id, user)
    risk = _mission_risk(db, engagement, risk_id)
    set_links(db, risk, [])
    risk.deleted_at = datetime.now(UTC)
    risk.deleted_by = user.id
    db.commit()


@router.post("/{engagement_id}/controls", response_model=ControlOut, status_code=201)
def add_control(
    engagement_id: uuid.UUID, body: MissionControlIn, user: CurrentUser, db: DbSession
) -> ControlOut:
    engagement = editable(db, engagement_id, user)
    risks = [_mission_risk(db, engagement, rid) for rid in body.risk_ids]
    if body.library_control_id:
        source = db.scalar(
            select(Control).where(
                Control.id == body.library_control_id,
                Control.bibliotheque.is_(True),
                Control.deleted_at.is_(None),
            )
        )
        if source is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Contrôle introuvable dans la bibliothèque"
            )
        control = copy_control(db, engagement, source)
    else:
        values = body.model_dump(mode="json", include=set(CONTROL_FIELDS))
        required = ("libelle", "cycle", "type_controle", "nature", "frequence")
        if not all(values.get(f) for f in required):
            raise HTTPException(422, "Libellé, cycle, type, nature et fréquence sont obligatoires")
        control = Control(**values, bibliotheque=False, engagement_id=engagement.id)
        db.add(control)
        db.flush()
    for risk in risks:
        current = [c.id for c in linked_controls(db, [risk.id])[risk.id]]
        if control.id not in current:
            db.add(RiskControl(risk_id=risk.id, control_id=control.id))
    db.commit()
    return control_out(control, procedures_by_control(db, [control.id])[control.id])


@router.patch("/{engagement_id}/controls/{control_id}", response_model=ControlOut)
def update_control(
    engagement_id: uuid.UUID,
    control_id: uuid.UUID,
    body: ControlUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ControlOut:
    engagement = editable(db, engagement_id, user)
    control = mission_control(db, engagement, control_id)
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        if value is not None or key == "description":
            setattr(control, key, value)
    db.commit()
    return control_out(control, procedures_by_control(db, [control.id])[control.id])


@router.delete("/{engagement_id}/controls/{control_id}", status_code=204)
def delete_control(
    engagement_id: uuid.UUID, control_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    engagement = editable(db, engagement_id, user)
    control = mission_control(db, engagement, control_id)
    now = datetime.now(UTC)
    for link in db.scalars(
        select(RiskControl).where(
            RiskControl.control_id == control.id, RiskControl.deleted_at.is_(None)
        )
    ):
        link.deleted_at = now
    for p in procedures_by_control(db, [control.id])[control.id]:
        p.deleted_at = now
    control.deleted_at = now
    control.deleted_by = user.id
    db.commit()


@router.post("/{engagement_id}/procedures", response_model=ProcedureOut, status_code=201)
def create_procedure(
    engagement_id: uuid.UUID, body: ProcedureIn, user: CurrentUser, db: DbSession
) -> Procedure:
    engagement = editable(db, engagement_id, user)
    control = mission_control(db, engagement, body.control_id)
    procedure = add_procedure(db, engagement, control, body.description, body.type_test.value)
    db.commit()
    return procedure


@router.patch("/{engagement_id}/procedures/{procedure_id}", response_model=ProcedureOut)
def update_procedure(
    engagement_id: uuid.UUID,
    procedure_id: uuid.UUID,
    body: ProcedureUpdate,
    user: CurrentUser,
    db: DbSession,
) -> Procedure:
    engagement = editable(db, engagement_id, user)
    procedure = mission_procedure(db, engagement, procedure_id)
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        if value is not None:
            setattr(procedure, key, value)
    db.commit()
    return procedure


@router.delete("/{engagement_id}/procedures/{procedure_id}", status_code=204)
def delete_procedure(
    engagement_id: uuid.UUID, procedure_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    engagement = editable(db, engagement_id, user)
    procedure = mission_procedure(db, engagement, procedure_id)
    procedure.deleted_at = datetime.now(UTC)
    procedure.deleted_by = user.id
    db.commit()


ASSIGNABLE = {
    MissionRole.CHEF,
    MissionRole.AUDITEUR,
    MissionRole.DATA_ANALYST,
    MissionRole.SUPERVISEUR,
}


@router.put("/{engagement_id}/procedures/{procedure_id}/assignment", response_model=ProcedureOut)
def assign_procedure(
    engagement_id: uuid.UUID,
    procedure_id: uuid.UUID,
    body: AssignmentIn,
    user: CurrentUser,
    db: DbSession,
) -> Procedure:
    """AUD-12 : affectation à un membre de l'équipe, échéance dans la période de la mission."""
    engagement = editable(db, engagement_id, user)
    procedure = mission_procedure(db, engagement, procedure_id)
    if body.assigne_a is not None:
        member = next((m for m in engagement.members if m.user_id == body.assigne_a), None)
        if member is None or MissionRole(member.role_mission) not in ASSIGNABLE:
            raise HTTPException(422, "La procédure doit être confiée à un membre de l'équipe")
    if body.echeance is not None and not (
        engagement.date_debut <= body.echeance <= engagement.date_fin
    ):
        raise HTTPException(422, "L'échéance doit tomber pendant la mission")
    procedure.assigne_a = body.assigne_a
    procedure.echeance = body.echeance
    db.commit()
    db.refresh(procedure)
    return procedure


@router.put("/{engagement_id}/procedures/{procedure_id}/status", response_model=ProcedureOut)
def procedure_status(
    engagement_id: uuid.UUID,
    procedure_id: uuid.UUID,
    body: ProcedureStatusIn,
    user: CurrentUser,
    db: DbSession,
) -> Procedure:
    """Avancement déclaré par la personne affectée, ou par le chef de mission."""
    engagement = get_engagement(db, engagement_id, user)
    ensure_open(engagement)
    procedure = mission_procedure(db, engagement, procedure_id)
    if procedure.assigne_a != user.id and not can_manage(engagement, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seule la personne affectée met à jour l'avancement"
        )
    procedure.statut = body.statut.value
    db.commit()
    db.refresh(procedure)
    return procedure


my_router = APIRouter(prefix="/me", tags=["Programme de travail"])


@my_router.get("/procedures", response_model=list[MyProcedureOut])
def my_procedures(user: CurrentUser, db: DbSession, a_faire: bool = True) -> list[dict]:
    """Procédures confiées à l'utilisateur, triées par échéance."""
    query = (
        select(Procedure, Engagement, Control)
        .join(Engagement, Engagement.id == Procedure.engagement_id)
        .join(Control, Control.id == Procedure.control_id)
        .where(
            Procedure.assigne_a == user.id,
            Procedure.deleted_at.is_(None),
            Engagement.deleted_at.is_(None),
            Engagement.id.in_(visible_engagements(user).with_only_columns(Engagement.id)),
        )
        .order_by(Procedure.echeance.nulls_last(), Procedure.reference)
    )
    if a_faire:
        query = query.where(Procedure.statut != ProcedureStatus.TERMINEE.value)
    return [
        {
            **ProcedureOut.model_validate(p).model_dump(),
            "engagement_id": e.id,
            "engagement_reference": e.reference,
            "engagement_titre": e.titre,
            "controle": c.libelle,
        }
        for p, e, c in db.execute(query)
    ]
