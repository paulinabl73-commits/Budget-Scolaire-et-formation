"""Rapport de mission (REP-02) : modèle, synthèse et conclusion rédigées par l'équipe ;
génération en PDF et Word (synthèse, constats, réponses des audités, plans d'action)."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.findings import can_write, require_writer
from app.api.mission_access import get_engagement
from app.api.opinion import MEDIA
from app.api.report_templates import default_template, get_template
from app.audit.listeners import record_event
from app.models.engagement import Engagement
from app.models.report import MissionReport
from app.models.user import User
from app.reporting.mission_report import build
from app.revision import documents

router = APIRouter(tags=["Rapports de mission"])


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


def report_out(db: Session, engagement: Engagement, r: MissionReport, user: User) -> dict:
    template = get_template(db, r.template_id)
    return {
        "id": str(r.id),
        "template_id": str(r.template_id),
        "modele": template.nom,
        "synthese": r.synthese,
        "conclusion": r.conclusion,
        "peut_rediger": can_write(engagement, user) and engagement.statut != "cloturee",
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
