"""Plans d'action des constats (CON-05) et leur vérification par l'audit (CON-07).

Le suivi se poursuit après la clôture de la mission : les écritures sur les plans ne
passent pas par ensure_open, seulement par les droits sur la mission.
"""

import datetime as dt
import uuid
from pathlib import PurePath

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.attachments import ALLOWED
from app.api.deps import CurrentUser, DbSession, user_from_request
from app.api.findings import can_write, get_finding
from app.api.mission_access import can_manage, get_engagement
from app.audit.listeners import record_event
from app.config import get_settings
from app.models.engagement import Engagement
from app.models.finding import (
    CLOSED_PLAN_STATUSES,
    ActionPlan,
    ActionPlanStatus,
    Finding,
    FindingStatus,
    PlanEvidence,
    Postponement,
)
from app.models.user import User
from app.notify import notify
from app.schemas_finding import PlanIn, PlanOut, PlanStatusIn, PlanUpdate
from app.security.roles import Perm, Role, has_permission
from app.signing import sign, verify
from app.storage import TooLarge, get_storage

router = APIRouter(tags=["Plans d'action"])

S = ActionPlanStatus


def is_owner(plan: ActionPlan, finding: Finding, user: User) -> bool:
    """Responsable du plan ou audité destinataire du constat."""
    return user.id in (plan.responsable_id, finding.audite_id)


def transitions(
    plan: ActionPlan, finding: Finding, engagement: Engagement, user: User
) -> list[str]:
    """Statuts accessibles à l'utilisateur depuis le statut courant du plan."""
    current = plan.statut
    if current in CLOSED_PLAN_STATUSES:
        return []
    auditor = can_write(engagement, user) or can_manage(engagement, user)
    owner = is_owner(plan, finding, user)
    allowed: list[str] = []
    if auditor or owner:
        allowed += {
            S.A_LANCER.value: [S.EN_COURS.value, S.REALISE.value],
            S.EN_COURS.value: [S.REALISE.value],
            S.REALISE.value: [S.EN_COURS.value] if owner else [],
        }[current]
    if auditor and current == S.REALISE.value:
        allowed.append(S.VERIFIE.value)  # CON-07 : vérification par l'audit
    if can_manage(engagement, user):
        allowed.append(S.RISQUE_ACCEPTE.value)  # décision tracée, justification obligatoire
    return list(dict.fromkeys(allowed))


def plan_out(db: Session, plan: ActionPlan, user: User | None = None) -> PlanOut:
    out = PlanOut.model_validate(plan)
    finding = db.get(Finding, plan.finding_id)
    out.responsable = db.get(User, plan.responsable_id).nom if plan.responsable_id else None
    out.responsable = out.responsable or plan.responsable_nom
    out.en_retard = plan.statut not in CLOSED_PLAN_STATUSES + (S.REALISE.value,) and (
        plan.echeance < dt.date.today()
    )
    out.constat_reference, out.constat_titre = finding.reference, finding.titre
    out.mission_id = finding.engagement_id
    if user is not None:
        engagement = db.get(Engagement, finding.engagement_id)
        out.transitions = transitions(plan, finding, engagement, user)
    return out


def _check_responsable(db: Session, data: dict) -> None:
    if data.get("responsable_id"):
        person = db.get(User, data["responsable_id"])
        if person is None or not person.actif:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Responsable inconnu")


def get_plan(db: Session, plan_id: uuid.UUID) -> ActionPlan:
    plan = db.scalar(
        select(ActionPlan).where(ActionPlan.id == plan_id, ActionPlan.deleted_at.is_(None))
    )
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan d'action introuvable")
    return plan


def plan_context(db: Session, plan: ActionPlan, user: User) -> tuple[Finding, Engagement]:
    """Accès au plan : membres de la mission (et Directeur), ou responsable / audité."""
    finding = db.get(Finding, plan.finding_id)
    if user.role == Role.AUDITE.value:
        if not is_owner(plan, finding, user):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan d'action introuvable")
        return finding, db.get(Engagement, finding.engagement_id)
    finding, engagement = get_finding(db, finding.id, user)
    return finding, engagement


def require_auditor(engagement: Engagement, user: User) -> None:
    if not (can_write(engagement, user) or can_manage(engagement, user)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux auditeurs et au chef de la mission"
        )


@router.get("/findings/{finding_id}/action-plans", response_model=list[PlanOut])
def list_plans(finding_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[PlanOut]:
    finding, _ = get_finding(db, finding_id, user)
    plans = db.scalars(
        select(ActionPlan)
        .where(ActionPlan.finding_id == finding.id, ActionPlan.deleted_at.is_(None))
        .order_by(ActionPlan.echeance, ActionPlan.created_at)
    )
    return [plan_out(db, p, user) for p in plans]


@router.post(
    "/findings/{finding_id}/action-plans",
    response_model=PlanOut,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(finding_id: uuid.UUID, body: PlanIn, user: CurrentUser, db: DbSession) -> PlanOut:
    finding, engagement = get_finding(db, finding_id, user)
    require_auditor(engagement, user)
    data = body.model_dump()
    _check_responsable(db, data)
    plan = ActionPlan(finding_id=finding.id, **data)
    db.add(plan)
    db.commit()
    return plan_out(db, plan, user)


@router.patch("/action-plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, body: PlanUpdate, user: CurrentUser, db: DbSession) -> PlanOut:
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    require_auditor(engagement, user)
    if plan.statut in CLOSED_PLAN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan clos : modification impossible")
    data = body.model_dump(exclude_unset=True)
    if "echeance" in data and finding.statut == FindingStatus.VALIDE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Constat validé : l'échéance ne change que par une demande de report (CON-08)",
        )
    _check_responsable(db, data)
    for key, value in data.items():
        setattr(plan, key, value)
    db.commit()
    return plan_out(db, plan, user)


@router.post("/action-plans/{plan_id}/status", response_model=PlanOut)
def change_status(
    plan_id: uuid.UUID, body: PlanStatusIn, user: CurrentUser, db: DbSession
) -> PlanOut:
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    if body.statut not in transitions(plan, finding, engagement, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Changement de statut non permis")
    if body.statut == S.RISQUE_ACCEPTE.value and not (body.commentaire or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Justification obligatoire pour accepter le risque",
        )
    plan.statut = body.statut
    if body.commentaire:
        plan.commentaire = body.commentaire
    if body.statut == S.VERIFIE.value:
        plan.verifie_le, plan.verifie_par = dt.datetime.now(dt.UTC), user.id
        notify(
            db,
            {u for u in (plan.responsable_id, finding.audite_id) if u},
            "plan_verifie",
            f"{finding.reference} : plan d'action clôturé",
            f"L'audit a vérifié et clôturé le plan « {plan.description[:200]} ».",
            lien=f"/portail/constats/{finding.id}",
        )
    db.commit()
    return plan_out(db, plan, user)


@router.get("/engagements/{engagement_id}/action-plans", response_model=list[PlanOut])
def mission_plans(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[PlanOut]:
    """Suivi des plans d'action de la mission (tous constats confondus)."""
    engagement = get_engagement(db, engagement_id, user)
    if not has_permission(user.role, Perm.FINDINGS_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    plans = db.scalars(
        select(ActionPlan)
        .join(Finding, Finding.id == ActionPlan.finding_id)
        .where(
            Finding.engagement_id == engagement.id,
            Finding.deleted_at.is_(None),
            ActionPlan.deleted_at.is_(None),
        )
        .order_by(ActionPlan.echeance)
    )
    return [plan_out(db, p, user) for p in plans]


# --- CON-07 : justificatifs, vérification ou rejet par l'audit ------------------------------


def evidence_out(e: PlanEvidence) -> dict:
    expires, sig = sign(f"plan-evidence:{e.id}")
    return {
        "id": str(e.id),
        "nom_fichier": e.nom_fichier,
        "taille": e.taille,
        "sha256": e.sha256,
        "commentaire": e.commentaire,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "url": f"/api/plan-evidence/{e.id}/content?expires={expires}&sig={sig}",
    }


@router.get("/action-plans/{plan_id}/evidence")
def list_plan_evidence(plan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict]:
    plan = get_plan(db, plan_id)
    plan_context(db, plan, user)
    rows = db.scalars(
        select(PlanEvidence)
        .where(PlanEvidence.action_plan_id == plan.id, PlanEvidence.deleted_at.is_(None))
        .order_by(PlanEvidence.created_at)
    )
    return [evidence_out(e) for e in rows]


@router.post("/action-plans/{plan_id}/evidence", status_code=status.HTTP_201_CREATED)
def upload_plan_evidence(
    plan_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUser,
    db: DbSession,
    commentaire: str | None = Form(default=None),
) -> dict:
    """Dépôt d'un justificatif par le responsable, l'audité ou l'équipe d'audit."""
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    if not (is_owner(plan, finding, user) or can_write(engagement, user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    if plan.statut in CLOSED_PLAN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan clos")
    name = PurePath(file.filename or "fichier").name[:255]
    ext = PurePath(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Format non admis : PDF, Excel, Word, CSV, texte ou image")
    content_type, magics = ALLOWED[ext]
    head = file.file.read(8)
    file.file.seek(0)
    if magics and not any(head.startswith(m) for m in magics):
        raise HTTPException(415, "Le contenu du fichier ne correspond pas à son extension")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    try:
        stored = get_storage().put(
            f"plans/{plan.id}/{uuid.uuid4()}{ext}", file.file, max_bytes=max_bytes
        )
    except TooLarge as exc:
        raise HTTPException(413, f"Fichier trop volumineux ({max_bytes // 2**20} Mo)") from exc
    evidence = PlanEvidence(
        action_plan_id=plan.id, nom_fichier=name, content_type=content_type, taille=stored.size,
        sha256=stored.sha256, storage_key=stored.key, commentaire=commentaire,
    )  # fmt: skip
    db.add(evidence)
    if is_owner(plan, finding, user):  # l'équipe est prévenue d'un dépôt de l'audité
        notify(
            db,
            _team_ids(engagement, finding),
            "plan_justificatif",
            f"{finding.reference} : justificatif déposé",
            f"{user.nom} a déposé « {name} » pour le plan « {plan.description[:200]} ».",
            lien=f"/missions/{engagement.id}/constats/{finding.id}",
        )
    db.commit()
    return evidence_out(evidence)


@router.get("/plan-evidence/{evidence_id}/content")
def download_plan_evidence(
    evidence_id: uuid.UUID,
    request: Request,
    db: DbSession,
    expires: int | None = None,
    sig: str | None = None,
) -> StreamingResponse:
    evidence = db.scalar(
        select(PlanEvidence).where(
            PlanEvidence.id == evidence_id, PlanEvidence.deleted_at.is_(None)
        )
    )
    if evidence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Justificatif introuvable")
    if not (expires and sig and verify(f"plan-evidence:{evidence.id}", expires, sig)):
        user = user_from_request(request, db)
        plan_context(db, get_plan(db, evidence.action_plan_id), user)
    record_event(db, "download", object_type="PlanEvidence", object_id=evidence.id)
    db.commit()
    filename = evidence.nom_fichier.replace('"', "")
    return StreamingResponse(
        get_storage().open(evidence.storage_key),
        media_type=evidence.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": evidence.sha256,
        },
    )


class RejectIn(BaseModel):
    commentaire: str = Field(min_length=1, max_length=4000)


@router.post("/action-plans/{plan_id}/reject", response_model=PlanOut)
def reject(plan_id: uuid.UUID, body: RejectIn, user: CurrentUser, db: DbSession) -> PlanOut:
    """CON-07 : l'audit refuse la réalisation déclarée ; le plan repart en cours."""
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    require_auditor(engagement, user)
    if plan.statut != S.REALISE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un plan déclaré réalisé se rejette")
    plan.statut, plan.commentaire = S.EN_COURS.value, f"Rejeté par l'audit : {body.commentaire}"
    notify(
        db,
        {u for u in (plan.responsable_id, finding.audite_id) if u},
        "plan_rejete",
        f"{finding.reference} : réalisation non acceptée",
        f"L'audit n'a pas validé la réalisation du plan « {plan.description[:200]} » : "
        f"{body.commentaire}",
        lien=f"/portail/constats/{finding.id}",
    )
    db.commit()
    return plan_out(db, plan, user)


def _team_ids(engagement: Engagement, finding: Finding) -> set[uuid.UUID]:
    from app.models.engagement import MissionRole

    chefs = {m.user_id for m in engagement.members if m.role_mission == MissionRole.CHEF}
    return chefs | ({finding.created_by} if finding.created_by else set())


# --- CON-08 : reports d'échéance -----------------------------------------------------------


class PostponeIn(BaseModel):
    nouvelle_echeance: dt.date
    motif: str = Field(min_length=1, max_length=4000)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(accepte|refuse)$")
    commentaire: str | None = Field(default=None, max_length=4000)


def postponement_out(db: Session, p: Postponement) -> dict:
    requester = db.get(User, p.created_by) if p.created_by else None
    decider = db.get(User, p.decide_par) if p.decide_par else None
    return {
        "id": str(p.id),
        "action_plan_id": str(p.action_plan_id),
        "ancienne_echeance": p.ancienne_echeance.isoformat(),
        "nouvelle_echeance": p.nouvelle_echeance.isoformat(),
        "motif": p.motif,
        "statut": p.statut,
        "demande_par": requester.nom if requester else None,
        "demande_le": p.created_at.isoformat() if p.created_at else None,
        "decide_par": decider.nom if decider else None,
        "decide_le": p.decide_le.isoformat() if p.decide_le else None,
        "commentaire_decision": p.commentaire_decision,
    }


@router.get("/action-plans/{plan_id}/postponements")
def list_postponements(plan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict]:
    plan = get_plan(db, plan_id)
    plan_context(db, plan, user)
    rows = db.scalars(
        select(Postponement)
        .where(Postponement.action_plan_id == plan.id, Postponement.deleted_at.is_(None))
        .order_by(Postponement.created_at)
    )
    return [postponement_out(db, p) for p in rows]


@router.post("/action-plans/{plan_id}/postponements", status_code=status.HTTP_201_CREATED)
def request_postponement(
    plan_id: uuid.UUID, body: PostponeIn, user: CurrentUser, db: DbSession
) -> dict:
    plan = get_plan(db, plan_id)
    finding, engagement = plan_context(db, plan, user)
    if not (is_owner(plan, finding, user) or can_write(engagement, user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    if plan.statut in CLOSED_PLAN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan clos")
    if body.nouvelle_echeance <= plan.echeance:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La nouvelle échéance doit suivre l'actuelle"
        )
    pending = db.scalar(
        select(Postponement).where(
            Postponement.action_plan_id == plan.id,
            Postponement.statut == "demande",
            Postponement.deleted_at.is_(None),
        )
    )
    if pending is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Une demande de report est déjà en attente")
    request = Postponement(
        action_plan_id=plan.id,
        ancienne_echeance=plan.echeance,
        nouvelle_echeance=body.nouvelle_echeance,
        motif=body.motif,
    )
    db.add(request)
    chefs = {m.user_id for m in engagement.members if m.role_mission == "chef_mission"}
    notify(
        db,
        chefs,
        "report_demande",
        f"{finding.reference} : demande de report au {body.nouvelle_echeance:%d/%m/%Y}",
        f"{user.nom} demande le report du plan « {plan.description[:200]} » "
        f"(échéance du {plan.echeance:%d/%m/%Y}) : {body.motif}",
        lien=f"/missions/{engagement.id}/constats/{finding.id}",
    )
    db.commit()
    return postponement_out(db, request)


@router.post("/postponements/{postponement_id}/decision")
def decide(postponement_id: uuid.UUID, body: DecisionIn, user: CurrentUser, db: DbSession) -> dict:
    """Décision du chef de mission (ou du Directeur) : le report accepté change l'échéance
    et relance le calendrier des rappels."""
    request = db.scalar(
        select(Postponement).where(
            Postponement.id == postponement_id, Postponement.deleted_at.is_(None)
        )
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable")
    plan = get_plan(db, request.action_plan_id)
    finding, engagement = plan_context(db, plan, user)
    if not can_manage(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Décision réservée au chef de mission")
    if request.statut != "demande":
        raise HTTPException(status.HTTP_409_CONFLICT, "Demande déjà traitée")
    request.statut = body.decision
    request.decide_par, request.decide_le = user.id, dt.datetime.now(dt.UTC)
    request.commentaire_decision = body.commentaire
    verdict = "accepté" if body.decision == "accepte" else "refusé"
    if body.decision == "accepte":
        request.relances_precedentes = plan.relances
        plan.echeance, plan.relances = request.nouvelle_echeance, []
    notify(
        db,
        {u for u in (request.created_by, plan.responsable_id, finding.audite_id) if u},
        f"report_{body.decision}",
        f"{finding.reference} : report {verdict}",
        f"La demande de report au {request.nouvelle_echeance:%d/%m/%Y} du plan "
        f"« {plan.description[:200]} » est {verdict}e"
        + (f" : {body.commentaire}" if body.commentaire else "."),
        lien=f"/portail/constats/{finding.id}",
    )
    db.commit()
    return postponement_out(db, request)
