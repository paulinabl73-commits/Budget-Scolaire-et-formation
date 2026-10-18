"""Mission d'inspection CIPRES (CIP-08), sur les constats du Module 3.

1. Suivi des recommandations des inspections précédentes de l'organisme (même entité).
2. Rapport provisoire : tous les constats ont été soumis à la phase contradictoire (CON-04) ;
   il fixe la date limite des observations de l'organisme.
3. Réponses de l'organisme : par constat (portail, CON-04) et réponse générale enregistrée.
4. Rapport définitif à la Commission de surveillance : constats validés, réponses et position
   de l'inspection, suivi des recommandations antérieures renseigné.
Chaque rapport est figé à son émission (blocs et empreinte SHA-256) ; les exports PDF et Word
sont produits à partir du contenu figé.
"""

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import can_manage, ensure_open, get_engagement, require_manager
from app.audit.listeners import record_event
from app.models.engagement import Engagement, MissionRole
from app.models.finding import (
    ActionPlan,
    Finding,
    FindingStatus,
    FollowUpStatus,
    InspectionReport,
    RecommendationFollowUp,
)
from app.models.universe import AuditableEntity
from app.revision import documents

router = APIRouter(tags=["Inspection CIPRES"])
MODE = "inspection_cipres"
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
CRITICITE = {"faible": "Faible", "moyenne": "Moyenne", "elevee": "Élevée", "critique": "Critique"}
POSITION = {"accord": "Accord", "accord_partiel": "Accord partiel", "desaccord": "Désaccord"}
SUIVI = {
    "mise_en_oeuvre": "Mise en œuvre",
    "partielle": "Partiellement mise en œuvre",
    "non_mise_en_oeuvre": "Non mise en œuvre",
    "sans_objet": "Devenue sans objet",
}


class FollowUpIn(BaseModel):
    statut: FollowUpStatus
    commentaire: str | None = Field(default=None, max_length=5000)


class ProvisionalIn(BaseModel):
    date_limite_reponse: dt.date


class ResponseIn(BaseModel):
    reponse: str = Field(min_length=1, max_length=50000)
    recue_le: dt.date


class FinalIn(BaseModel):
    destinataire: str = Field(
        default="Commission de surveillance de la CIPRES", min_length=3, max_length=300
    )


def get_inspection(db: Session, engagement_id: uuid.UUID, user: Any) -> Engagement:
    engagement = get_engagement(db, engagement_id, user)
    if engagement.mode != MODE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mission qui n'est pas une inspection")
    return engagement


def _findings(db: Session, engagement: Engagement) -> list[Finding]:
    return list(
        db.scalars(
            select(Finding)
            .where(Finding.engagement_id == engagement.id, Finding.deleted_at.is_(None))
            .order_by(Finding.reference)
        )
    )


def _reports(db: Session, engagement: Engagement) -> dict[str, InspectionReport]:
    rows = db.scalars(
        select(InspectionReport).where(
            InspectionReport.engagement_id == engagement.id, InspectionReport.deleted_at.is_(None)
        )
    )
    return {r.version: r for r in rows}


def previous_recommendations(db: Session, engagement: Engagement) -> list[dict[str, Any]]:
    """Recommandations validées des inspections antérieures du même organisme, avec l'état
    de leurs plans d'action et le suivi noté dans cette inspection."""
    if engagement.entity_id is None:
        return []
    rows = db.execute(
        select(Finding, Engagement)
        .join(Engagement, Engagement.id == Finding.engagement_id)
        .where(
            Engagement.entity_id == engagement.entity_id,
            Engagement.mode == MODE,
            Engagement.id != engagement.id,
            Engagement.date_debut < engagement.date_debut,
            Engagement.deleted_at.is_(None),
            Finding.deleted_at.is_(None),
            Finding.statut == FindingStatus.VALIDE.value,
        )
        .order_by(Engagement.date_debut, Finding.reference)
    ).all()
    ids = [f.id for f, _ in rows]
    plans: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    for p in db.scalars(
        select(ActionPlan).where(ActionPlan.finding_id.in_(ids), ActionPlan.deleted_at.is_(None))
    ):
        plans[p.finding_id].append(p.statut)
    follow = {
        r.finding_id: r
        for r in db.scalars(
            select(RecommendationFollowUp).where(
                RecommendationFollowUp.engagement_id == engagement.id,
                RecommendationFollowUp.deleted_at.is_(None),
            )
        )
    }
    return [
        {
            "finding_id": str(f.id),
            "mission": e.reference,
            "reference": f.reference,
            "titre": f.titre,
            "criticite": f.criticite,
            "recommandation": f.recommandation,
            "plans": plans[f.id],
            "suivi": {"statut": follow[f.id].statut, "commentaire": follow[f.id].commentaire}
            if f.id in follow
            else None,
        }
        for f, e in rows
    ]


def _blockers(db: Session, engagement: Engagement, version: str) -> list[str]:
    findings = _findings(db, engagement)
    reports = _reports(db, engagement)
    out = []
    if version in reports:
        out.append(f"Rapport {version} déjà émis")
    if not findings:
        out.append("Aucun constat")
    if version == "provisoire":
        drafts = [f.reference for f in findings if f.statut == FindingStatus.BROUILLON.value]
        if drafts:
            out.append("Constats non soumis à l'organisme : " + ", ".join(drafts))
    else:
        if "provisoire" not in reports:
            out.append("Rapport provisoire non émis")
        pending = [f.reference for f in findings if f.statut != FindingStatus.VALIDE.value]
        if pending:
            out.append("Constats non validés : " + ", ".join(pending))
        missing = [
            r["reference"] for r in previous_recommendations(db, engagement) if not r["suivi"]
        ]
        if missing:
            out.append("Suivi non renseigné des recommandations : " + ", ".join(missing))
    return out


def _report_out(r: InspectionReport) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "version": r.version,
        "titre": r.titre,
        "emis_le": r.emis_le.isoformat(),
        "sha256": r.sha256,
        "destinataire": r.destinataire,
        "date_limite_reponse": r.date_limite_reponse.isoformat() if r.date_limite_reponse else None,
        "reponse_organisme": r.reponse_organisme,
        "reponse_recue_le": r.reponse_recue_le.isoformat() if r.reponse_recue_le else None,
    }


def overview(db: Session, engagement: Engagement, user: Any) -> dict[str, Any]:
    findings = _findings(db, engagement)
    manager = can_manage(engagement, user) and engagement.statut != "cloturee"
    return {
        "rapports": [_report_out(r) for r in _reports(db, engagement).values()],
        "constats": [
            {
                "id": str(f.id),
                "reference": f.reference,
                "titre": f.titre,
                "criticite": f.criticite,
                "statut": f.statut,
                "reponse_position": f.reponse_position,
            }
            for f in findings
        ],
        "recommandations_anterieures": previous_recommendations(db, engagement),
        "blocages": {v: _blockers(db, engagement, v) for v in ("provisoire", "definitif")},
        "peut_gerer": manager,
    }


def _team(engagement: Engagement) -> str:
    order = {MissionRole.CHEF.value: 0, MissionRole.AUDITEUR.value: 1}
    members = sorted(
        (m for m in engagement.members if m.role_mission in order),
        key=lambda m: (order[m.role_mission], m.user.nom),
    )
    return ", ".join(m.user.nom for m in members)


def build_blocks(
    db: Session, engagement: Engagement, version: str, provisional: InspectionReport | None
) -> list[dict[str, Any]]:
    entity = db.get(AuditableEntity, engagement.entity_id) if engagement.entity_id else None
    findings = _findings(db, engagement)
    blocks: list[dict[str, Any]] = [
        {
            "texte": f"Organisme contrôlé : {entity.nom if entity else '—'} — mission "
            f"{engagement.reference}, du {engagement.date_debut:%d/%m/%Y} au "
            f"{engagement.date_fin:%d/%m/%Y}."
        },
        {"texte": f"Équipe d'inspection : {_team(engagement) or '—'}."},
    ]
    if engagement.objectifs:
        blocks.append({"texte": f"Objet : {engagement.objectifs}"})
    counts = {k: sum(f.criticite == k for f in findings) for k in CRITICITE}
    blocks += [
        {"titre": "1. Synthèse"},
        {
            "texte": f"{len(findings)} constat(s) : "
            + ", ".join(f"{CRITICITE[k].lower()} {n}" for k, n in counts.items() if n)
            + "."
        },
        {"titre": "2. Suivi des recommandations de la précédente inspection"},
    ]
    previous = previous_recommendations(db, engagement)
    if previous:
        blocks.append(
            {
                "tableau": [["Mission", "Réf.", "Recommandation", "Suivi", "Commentaire"]]
                + [
                    [
                        r["mission"],
                        r["reference"],
                        r["recommandation"] or r["titre"],
                        SUIVI[r["suivi"]["statut"]] if r["suivi"] else "À apprécier",
                        (r["suivi"] or {}).get("commentaire") or "",
                    ]
                    for r in previous
                ]
            }
        )
    else:
        blocks.append({"texte": "Première inspection de l'organisme : sans objet."})
    blocks.append({"titre": "3. Constats et recommandations"})
    for f in findings:
        blocks.append(
            {"titre": f"{f.reference} — {f.titre} (criticité {CRITICITE[f.criticite].lower()})"}
        )
        for label, value in (
            ("Référence (critère)", f.critere),
            ("Constat", f.constat),
            ("Cause", f.cause),
            ("Conséquence", f.consequence),
            ("Recommandation", f.recommandation),
        ):
            if value:
                blocks.append({"texte": f"{label} : {value}"})
        if version == "definitif":
            position = POSITION.get(f.reponse_position or "", "Pas de réponse dans le délai")
            answer = f" — {f.reponse_commentaire}" if f.reponse_commentaire else ""
            blocks.append({"texte": f"Réponse de l'organisme : {position}{answer}"})
            if f.commentaire_validation:
                blocks.append({"texte": f"Position de l'inspection : {f.commentaire_validation}"})
    if version == "provisoire":
        blocks += [
            {"titre": "4. Procédure contradictoire"},
            {
                "texte": "Ce rapport provisoire est communiqué à l'organisme, invité à faire part "
                "de ses observations sur chaque constat avant le "
                f"{provisional.date_limite_reponse:%d/%m/%Y}."  # type: ignore[union-attr]
            },
        ]
    else:
        blocks += [
            {"titre": "4. Réponse générale de l'organisme"},
            {
                "texte": f"Reçue le {provisional.reponse_recue_le:%d/%m/%Y} : "
                f"{provisional.reponse_organisme}"
                if provisional and provisional.reponse_organisme
                else "Aucune réponse générale reçue."
            },
        ]
    return blocks


def _issue(
    db: Session, engagement: Engagement, user: Any, version: str, **fields: Any
) -> InspectionReport:
    entity = db.get(AuditableEntity, engagement.entity_id) if engagement.entity_id else None
    label = "provisoire" if version == "provisoire" else "définitif"
    title = f"Rapport {label} d'inspection — {entity.nom if entity else engagement.titre}"
    provisional = _reports(db, engagement).get("provisoire")
    report = InspectionReport(
        engagement_id=engagement.id,
        version=version,
        titre=title,
        blocs=[],
        sha256="",
        emis_le=dt.datetime.now(dt.UTC),
        emis_par=user.id,
        **fields,
    )
    report.blocs = build_blocks(
        db, engagement, version, report if version == "provisoire" else provisional
    )
    if version == "definitif":
        report.blocs.insert(0, {"texte": f"Destinataire : {report.destinataire}."})
    canonical = json.dumps([title, report.blocs], ensure_ascii=False, sort_keys=True)
    report.sha256 = hashlib.sha256(canonical.encode()).hexdigest()
    db.add(report)
    db.flush()
    record_event(
        db,
        "emission",
        object_type="InspectionReport",
        object_id=report.id,
        details={"version": version, "sha256": report.sha256},
    )
    return report


def _require_inspector(db: Session, engagement_id: uuid.UUID, user: Any) -> Engagement:
    engagement = get_inspection(db, engagement_id, user)
    ensure_open(engagement)
    require_manager(engagement, user)
    return engagement


@router.get("/engagements/{engagement_id}/inspection")
def read_inspection(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return overview(db, get_inspection(db, engagement_id, user), user)


@router.put("/engagements/{engagement_id}/inspection/follow-ups/{finding_id}")
def set_follow_up(
    engagement_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: FollowUpIn,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    engagement = _require_inspector(db, engagement_id, user)
    if "definitif" in _reports(db, engagement):
        raise HTTPException(status.HTTP_409_CONFLICT, "Rapport définitif émis")
    if str(finding_id) not in {r["finding_id"] for r in previous_recommendations(db, engagement)}:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Recommandation d'une inspection antérieure introuvable"
        )
    row = db.scalar(
        select(RecommendationFollowUp).where(
            RecommendationFollowUp.engagement_id == engagement.id,
            RecommendationFollowUp.finding_id == finding_id,
            RecommendationFollowUp.deleted_at.is_(None),
        )
    )
    if row is None:
        row = RecommendationFollowUp(engagement_id=engagement.id, finding_id=finding_id, statut="")
        db.add(row)
    row.statut, row.commentaire = body.statut.value, body.commentaire
    db.commit()
    return overview(db, engagement, user)


@router.post("/engagements/{engagement_id}/inspection/provisional", status_code=201)
def issue_provisional(
    engagement_id: uuid.UUID, body: ProvisionalIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = _require_inspector(db, engagement_id, user)
    blockers = _blockers(db, engagement, "provisoire")
    if blockers:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": "; ".join(blockers), "points": blockers}
        )
    if body.date_limite_reponse <= dt.date.today():
        raise HTTPException(422, "La date limite de réponse doit être postérieure à ce jour")
    report = _issue(
        db, engagement, user, "provisoire", date_limite_reponse=body.date_limite_reponse
    )
    db.commit()
    return _report_out(report)


@router.put("/engagements/{engagement_id}/inspection/response")
def record_response(
    engagement_id: uuid.UUID, body: ResponseIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = _require_inspector(db, engagement_id, user)
    reports = _reports(db, engagement)
    if "provisoire" not in reports:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rapport provisoire non émis")
    if "definitif" in reports:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rapport définitif émis")
    provisional = reports["provisoire"]
    if body.recue_le < provisional.emis_le.date():
        raise HTTPException(422, "Réponse antérieure à l'émission du rapport provisoire")
    provisional.reponse_organisme, provisional.reponse_recue_le = body.reponse, body.recue_le
    db.commit()
    return _report_out(provisional)


@router.post("/engagements/{engagement_id}/inspection/final", status_code=201)
def issue_final(
    engagement_id: uuid.UUID, body: FinalIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = _require_inspector(db, engagement_id, user)
    blockers = _blockers(db, engagement, "definitif")
    if blockers:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": "; ".join(blockers), "points": blockers}
        )
    report = _issue(db, engagement, user, "definitif", destinataire=body.destinataire)
    db.commit()
    return _report_out(report)


@router.get("/inspection-reports/{report_id}/export")
def export_report(
    report_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),  # noqa: A002
) -> Response:
    report = db.get(InspectionReport, report_id)
    if report is None or report.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rapport introuvable")
    get_engagement(db, report.engagement_id, user)
    content = documents.render(format, report.titre, report.blocs)
    record_event(
        db,
        "export",
        object_type="InspectionReport",
        object_id=report.id,
        details={"format": format},
    )
    db.commit()
    name = f"rapport_{report.version}_inspection.{format}"
    return Response(
        content,
        media_type=MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
