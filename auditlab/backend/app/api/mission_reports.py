"""Rapport de mission (REP-02) : modèle, synthèse et conclusion rédigées par l'équipe ;
génération en PDF et Word (synthèse, constats, réponses des audités, plans d'action).

Circuit (REP-03) : Projet (rédaction par l'équipe) → Revu (superviseur de la mission ou
Directeur, jamais le seul chef de mission) → Validé (Directeur) → Diffusé (Directeur ou chef de
mission, mission au statut « rapport »). Revu et Validé peuvent être renvoyés en projet avec un
motif. À la diffusion, le PDF et le Word sont générés une fois, stockés avec leur empreinte et
servis tels quels ensuite : la version diffusée est figée. La mission ne se clôture qu'après la
diffusion de son rapport.
"""

import datetime as dt
import io
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.engagement_status import GUARDS
from app.api.findings import can_write, require_writer
from app.api.mission_access import get_engagement, mission_role
from app.api.opinion import MEDIA
from app.api.report_templates import default_template, get_template
from app.audit.listeners import record_event
from app.models.engagement import Engagement, EngagementStatus, MissionRole
from app.models.report import MissionReport
from app.models.user import User
from app.notify import notify
from app.reporting.mission_report import build
from app.revision import documents
from app.security.roles import Perm, Role, has_permission
from app.storage import get_storage

router = APIRouter(tags=["Rapports de mission"])


class TransitionIn(BaseModel):
    statut: Literal["projet", "revu", "valide", "diffuse"]
    commentaire: str | None = Field(default=None, max_length=2000)


class ReportIn(BaseModel):
    template_id: uuid.UUID | None = None
    synthese: str | None = Field(default=None, max_length=20000)
    conclusion: str | None = Field(default=None, max_length=20000)


def get_report(db: Session, engagement: Engagement) -> MissionReport | None:
    return db.scalar(
        select(MissionReport).where(
            MissionReport.engagement_id == engagement.id, MissionReport.deleted_at.is_(None)
        )
    )


def ensure_report(db: Session, engagement: Engagement) -> MissionReport:
    report = get_report(db, engagement)
    if report is None:
        template = default_template(db)
        if template is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Aucun modèle de rapport par défaut")
        report = MissionReport(engagement_id=engagement.id, template_id=template.id)
        db.add(report)
        db.flush()
    return report


def _director(user: User) -> bool:
    return has_permission(user.role, Perm.REPORT_PUBLISH)


def allowed(engagement: Engagement, r: MissionReport, user: User) -> list[str]:
    """Statuts que l'utilisateur peut donner au rapport depuis son statut actuel."""
    reviewer = _director(user) or mission_role(engagement, user) == MissionRole.SUPERVISEUR
    chef = mission_role(engagement, user) == MissionRole.CHEF
    targets = {
        "projet": ["revu"] if reviewer else [],
        "revu": (["valide"] if _director(user) else []) + (["projet"] if reviewer else []),
        "valide": (["diffuse"] if _director(user) or chef else [])
        + (["projet"] if reviewer else []),
        "diffuse": [],
    }
    return targets[r.statut] if engagement.statut != "cloturee" else []


def report_out(db: Session, engagement: Engagement, r: MissionReport, user: User) -> dict:
    template = get_template(db, r.template_id)
    return {
        "id": str(r.id),
        "template_id": str(r.template_id),
        "modele": template.nom,
        "synthese": r.synthese,
        "conclusion": r.conclusion,
        "statut": r.statut,
        "historique": r.historique,
        "diffuse_le": r.diffuse_le.isoformat() if r.diffuse_le else None,
        "empreintes": {k: v["sha256"] for k, v in (r.fichiers or {}).items()},
        "transitions": allowed(engagement, r, user),
        "peut_rediger": r.statut == "projet"
        and can_write(engagement, user)
        and engagement.statut != "cloturee",
    }


@router.get("/engagements/{engagement_id}/report")
def read_report(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    engagement = get_engagement(db, engagement_id, user)
    report = ensure_report(db, engagement)
    db.commit()
    return report_out(db, engagement, report, user)


@router.put("/engagements/{engagement_id}/report")
def save_report(
    engagement_id: uuid.UUID, body: ReportIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = get_engagement(db, engagement_id, user)
    require_writer(engagement, user)
    report = ensure_report(db, engagement)
    if report.statut != "projet":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Rapport en revue ou diffusé : renvoyez-le en projet"
        )
    if body.template_id is not None:
        template = get_template(db, body.template_id)
        if not template.actif:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Modèle inactif")
        report.template_id = template.id
    report.synthese, report.conclusion = body.synthese, body.conclusion
    db.commit()
    return report_out(db, engagement, report, user)


def render(db: Session, engagement: Engagement, report: MissionReport, fmt: str) -> bytes:
    title, blocks, footer = build(db, engagement, report, get_template(db, report.template_id))
    return documents.render(fmt, title, blocks, footer)


@router.get("/engagements/{engagement_id}/report/document")
def download(
    engagement_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    engagement = get_engagement(db, engagement_id, user)
    report = ensure_report(db, engagement)
    stored = (report.fichiers or {}).get(format)
    if stored:  # version diffusée, figée
        content = b"".join(get_storage().open(stored["key"]))
    else:
        content = render(db, engagement, report, format)
    record_event(db, "export", object_type="MissionReport", object_id=report.id,
                 details={"format": format})  # fmt: skip
    db.commit()
    return Response(
        content,
        media_type=MEDIA[format],
        headers={
            "Content-Disposition": f'attachment; filename="rapport_{engagement.reference}.{format}"'
        },
    )


def _recipients(db: Session, engagement: Engagement, target: str) -> set[uuid.UUID]:
    team = {m.user_id for m in engagement.members}
    if target == "revu":
        return set(
            db.scalars(
                select(User.id).where(User.role == Role.DIRECTEUR.value, User.actif.is_(True))
            )
        )
    return team


@router.post("/engagements/{engagement_id}/report/transition")
def transition(
    engagement_id: uuid.UUID, body: TransitionIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = get_engagement(db, engagement_id, user)
    report = ensure_report(db, engagement)
    if body.statut not in allowed(engagement, report, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Passage de « {report.statut} » à « {body.statut} » non autorisé pour vous",
        )
    if body.statut == "projet" and not (body.commentaire or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Motif du renvoi obligatoire")
    now = dt.datetime.now(dt.UTC)
    if body.statut == "diffuse":
        if engagement.statut != EngagementStatus.RAPPORT.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Mission au statut « Rapport » attendue (constats validés)",
            )
        files = {}
        for fmt in ("pdf", "docx"):
            content = render(db, engagement, report, fmt)
            stored = get_storage().put(
                f"mission-reports/{engagement.id}/{report.id}.{fmt}", io.BytesIO(content)
            )
            files[fmt] = {"key": stored.key, "sha256": stored.sha256}
        report.fichiers, report.diffuse_le, report.diffuse_par = files, now, user.id
    step = {"de": report.statut, "vers": body.statut, "par": user.nom, "le": now.isoformat(),
            "commentaire": body.commentaire}  # fmt: skip
    report.historique = [*report.historique, step]
    report.statut = body.statut
    record_event(db, "transition", object_type="MissionReport", object_id=report.id,
                 details={"statut": body.statut})  # fmt: skip
    labels = {"projet": "renvoyé en projet", "revu": "revu", "valide": "validé",
              "diffuse": "diffusé"}  # fmt: skip
    notify(db, _recipients(db, engagement, body.statut) - {user.id}, "rapport_mission",
           f"Rapport {engagement.reference} {labels[body.statut]}",
           body.commentaire or f"Le rapport de la mission « {engagement.titre} » est "
           f"{labels[body.statut]}.", lien=f"/missions/{engagement.id}?onglet=rapport")  # fmt: skip
    db.commit()
    return report_out(db, engagement, report, user)


def _report_diffused(db: Session, engagement: Engagement) -> str | None:
    """Garde de clôture (AUD-07) : une mission d'audit se clôt sur son rapport diffusé."""
    if engagement.mode != "audit":
        return None
    report = get_report(db, engagement)
    if report is None or report.statut != "diffuse":
        return "Le rapport de mission doit être diffusé avant la clôture"
    return None


GUARDS[EngagementStatus.CLOTUREE].append(_report_diffused)
