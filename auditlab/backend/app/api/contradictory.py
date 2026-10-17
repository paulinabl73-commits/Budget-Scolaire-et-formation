"""Phase contradictoire des constats (CON-04).

1. L'équipe envoie le constat à un audité, avec une date limite de réponse.
2. L'audité répond (accord, accord partiel, désaccord motivé) et propose ses plans d'action.
3. Le chef de mission (ou le Directeur) valide le constat ; sans réponse, la validation n'est
   possible qu'après la date limite, et le rapport mentionne l'absence de réponse.
Le passage de la mission en « Rapport » exige que tous ses constats soient validés.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.engagement_status import GUARDS
from app.api.findings import finding_out, get_finding, require_writer
from app.api.mission_access import can_manage, ensure_open
from app.config import get_settings
from app.models.engagement import Engagement, EngagementStatus, MissionRole
from app.models.finding import ActionPlan, Finding, FindingStatus
from app.models.user import User
from app.notify import notify
from app.schemas_finding import FindingOut, ResponseIn, SendIn, ValidateIn
from app.security.roles import Perm, Role, has_permission

router = APIRouter(tags=["Constats"])


def _team(engagement: Engagement, finding: Finding) -> set[uuid.UUID]:
    chefs = {m.user_id for m in engagement.members if m.role_mission == MissionRole.CHEF}
    return chefs | ({finding.created_by} if finding.created_by else set())


@router.post("/findings/{finding_id}/send", response_model=FindingOut)
def send(finding_id: uuid.UUID, body: SendIn, user: CurrentUser, db: DbSession) -> FindingOut:
    finding, engagement = get_finding(db, finding_id, user)
    require_writer(engagement, user)
    if finding.statut != FindingStatus.BROUILLON.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un constat en brouillon s'envoie")
    if not (finding.constat and finding.recommandation):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Constat et recommandation requis avant envoi"
        )
    audite = db.get(User, body.audite_id)
    if audite is None or audite.role != Role.AUDITE.value or not audite.actif:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Destinataire : un audité actif")
    today = dt.date.today()
    deadline = body.date_limite_reponse or today + dt.timedelta(
        days=get_settings().delai_reponse_constat_jours
    )
    if deadline < today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Date limite dépassée")
    finding.statut = FindingStatus.ENVOYE.value
    finding.audite_id, finding.date_limite_reponse = audite.id, deadline
    finding.envoye_le = dt.datetime.now(dt.UTC)
    notify(
        db,
        [audite.id],
        "constat_envoye",
        f"Constat {finding.reference} à commenter avant le {deadline:%d/%m/%Y}",
        f"La mission « {engagement.titre} » vous soumet le constat « {finding.titre} ». "
        "Indiquez votre accord ou votre désaccord motivé et proposez un plan d'action.",
        lien=f"/portail/constats/{finding.id}",
    )
    db.commit()
    return finding_out(db, finding, engagement, user)


def respond_to(db: Session, finding: Finding, body: ResponseIn, user: User) -> None:
    """Réponse de l'audité ; partagée avec le portail (CON-09)."""
    if finding.statut != FindingStatus.ENVOYE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce constat n'attend pas de réponse")
    if body.position != "accord" and not (body.commentaire or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Un désaccord, même partiel, doit être motivé"
        )
    finding.reponse_position, finding.reponse_commentaire = body.position, body.commentaire
    finding.repondu_le, finding.repondu_par = dt.datetime.now(dt.UTC), user.id
    finding.statut = FindingStatus.REPONDU.value
    for plan in body.plans:
        db.add(
            ActionPlan(
                finding_id=finding.id,
                description=plan.description,
                responsable_id=None if plan.responsable_nom else user.id,
                responsable_nom=plan.responsable_nom,
                echeance=plan.echeance,
                propose_par_audite=True,
            )
        )
    engagement = db.get(Engagement, finding.engagement_id)
    notify(
        db,
        _team(engagement, finding),
        "constat_repondu",
        f"{engagement.reference} · réponse de l'audité sur {finding.reference}",
        f"{user.nom} a répondu au constat « {finding.titre} » ({body.position}) et proposé "
        f"{len(body.plans)} plan(s) d'action.",
        lien=f"/missions/{engagement.id}/constats/{finding.id}",
    )


@router.post("/findings/{finding_id}/response", response_model=FindingOut)
def respond(
    finding_id: uuid.UUID, body: ResponseIn, user: CurrentUser, db: DbSession
) -> FindingOut:
    """Réponse de l'audité destinataire (le portail CON-09 offre le même service)."""
    finding = db.scalar(
        select(Finding).where(Finding.id == finding_id, Finding.deleted_at.is_(None))
    )
    if (
        finding is None
        or finding.audite_id != user.id
        or not has_permission(user.role, Perm.FINDINGS_RESPOND)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Constat introuvable")
    respond_to(db, finding, body, user)
    db.commit()
    return FindingOut.model_validate(finding)


@router.post("/findings/{finding_id}/validate", response_model=FindingOut)
def validate(
    finding_id: uuid.UUID, body: ValidateIn, user: CurrentUser, db: DbSession
) -> FindingOut:
    finding, engagement = get_finding(db, finding_id, user)
    ensure_open(engagement)
    if not (can_manage(engagement, user) and has_permission(user.role, Perm.FINDINGS_VALIDATE)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de mission et au Directeur")
    no_answer = (
        finding.statut == FindingStatus.ENVOYE.value
        and finding.date_limite_reponse is not None
        and finding.date_limite_reponse < dt.date.today()
    )
    if finding.statut != FindingStatus.REPONDU.value and not no_answer:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Validation après la réponse de l'audité, ou après la date limite sans réponse",
        )
    if no_answer:
        finding.reponse_position = "sans_reponse"
    finding.statut = FindingStatus.VALIDE.value
    finding.valide_le, finding.valide_par = dt.datetime.now(dt.UTC), user.id
    finding.commentaire_validation = body.commentaire
    db.commit()
    return finding_out(db, finding, engagement, user)


def _findings_validated(db: Session, engagement: Engagement) -> str | None:
    pending = db.scalar(
        select(Finding.reference).where(
            Finding.engagement_id == engagement.id,
            Finding.deleted_at.is_(None),
            Finding.statut != FindingStatus.VALIDE.value,
        )
    )
    if pending:
        return f"Constat {pending} non validé : la phase contradictoire doit être terminée"
    return None


GUARDS[EngagementStatus.RAPPORT].append(_findings_validated)
