"""Modèles de rapports (REV-27), opinion du dossier, signature et émission (REV-28)."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.adjustments import unadjusted
from app.api.audit_files import get_file, require_direct
from app.api.deps import CurrentUser, DbSession, require
from app.audit.listeners import record_event
from app.config import get_settings
from app.models.revision import AccountingFramework, AuditFile, AuditOpinion, ReportTemplate
from app.models.universe import AuditableEntity
from app.models.user import User
from app.revision import documents, reports
from app.revision.formula import evaluate
from app.revision.mapping import UnmappedError, file_values
from app.security.roles import Perm

router = APIRouter(tags=["Révision – rapports"])
Reader = Annotated[User, Depends(require(Perm.REVISION_READ, Perm.FRAMEWORKS_MANAGE))]
Manager = Annotated[User, Depends(require(Perm.FRAMEWORKS_MANAGE))]
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SUGGESTION = {
    "non_significatif": "sans_reserve",
    "vigilance": "sans_reserve",
    "significatif": "avec_reserve",
}


class TemplateIn(BaseModel):
    sections: list[dict[str, Any]] = Field(min_length=1, max_length=50)


class Convention(BaseModel):
    objet: str = Field(min_length=3, max_length=500)
    parties: str = Field(min_length=2, max_length=500)
    modalites: str | None = Field(default=None, max_length=2000)
    montant: str | None = Field(default=None, max_length=60)


class OpinionIn(BaseModel):
    type_opinion: str = Field(pattern="^(" + "|".join(reports.OPINIONS) + ")$")
    fondement: str | None = Field(default=None, max_length=10000)
    observations: str | None = Field(default=None, max_length=10000)
    conventions: list[Convention] = Field(default_factory=list, max_length=100)
    lieu: str | None = Field(default=None, max_length=120)


def template_out(t: ReportTemplate) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "code": t.code,
        "nom": t.nom,
        "version": t.version,
        "sections": t.sections,
    }


@router.get("/report-templates")
def list_templates(user: Reader, db: DbSession) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ReportTemplate)
        .where(ReportTemplate.deleted_at.is_(None))
        .order_by(ReportTemplate.code)
    )
    return [template_out(t) for t in rows]


@router.put("/report-templates/{code}")
def update_template(code: str, body: TemplateIn, user: Manager, db: DbSession) -> dict[str, Any]:
    t = db.scalar(
        select(ReportTemplate).where(
            ReportTemplate.code == code, ReportTemplate.deleted_at.is_(None)
        )
    )
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle introuvable")
    for s in body.sections:
        if not isinstance(s.get("texte"), str) or s.get("si") not in (
            None,
            "observations",
            *reports.OPINIONS,
        ):
            raise HTTPException(
                422, "Section : texte obligatoire, condition parmi les types d'opinion"
            )
    t.sections, t.version = body.sections, t.version + 1
    db.commit()
    return template_out(t)


def get_opinion(db: Session, file: AuditFile) -> AuditOpinion | None:
    return db.scalar(
        select(AuditOpinion).where(
            AuditOpinion.audit_file_id == file.id, AuditOpinion.deleted_at.is_(None)
        )
    )


def _users(db: Session, *ids: uuid.UUID | None) -> list[str | None]:
    return [db.get(User, i).nom if i else None for i in ids]


def opinion_out(db: Session, file: AuditFile, user: User, o: AuditOpinion | None) -> dict[str, Any]:
    suggestion = None
    try:
        suggestion = SUGGESTION[unadjusted(file.id, user, db)["conclusion"]]
    except HTTPException:
        pass
    if o is None:
        return {
            "statut": "a_rediger",
            "type_opinion": suggestion or "sans_reserve",
            "fondement": None,
            "observations": None,
            "conventions": [],
            "lieu": None,
            "suggestion": suggestion,
        }
    signe, emis = _users(db, o.signe_par, o.emis_par)
    return {
        "statut": o.statut,
        "type_opinion": o.type_opinion,
        "fondement": o.fondement,
        "observations": o.observations,
        "conventions": o.conventions,
        "lieu": o.lieu,
        "suggestion": suggestion,
        "signe_par": signe,
        "emis_par": emis,
        "signe_le": o.signe_le.isoformat() if o.signe_le else None,
        "emis_le": o.emis_le.isoformat() if o.emis_le else None,
        "empreinte": o.empreinte,
        "archive_sha256": o.archive_sha256,
    }


@router.get("/audit-files/{file_id}/opinion")
def read_opinion(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return opinion_out(db, file, user, get_opinion(db, file))


@router.put("/audit-files/{file_id}/opinion")
def save_opinion(
    file_id: uuid.UUID, body: OpinionIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_direct(file, engagement, user)
    if body.type_opinion != "sans_reserve" and not (body.fondement or "").strip():
        raise HTTPException(422, "Le fondement de l'opinion modifiée est obligatoire")
    o = get_opinion(db, file)
    if o is not None and o.statut != "brouillon":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Opinion signée : annulez la signature pour la modifier"
        )
    if o is None:
        o = AuditOpinion(engagement_id=file.engagement_id, audit_file_id=file.id)
        db.add(o)
    data = body.model_dump()
    for key, value in data.items():
        setattr(o, key, value)
    db.commit()
    return opinion_out(db, file, user, o)


def context(db: Session, file: AuditFile, o: AuditOpinion, signer: str | None) -> dict[str, str]:
    fw = db.get(AccountingFramework, file.framework_id)
    try:
        values = file_values(db, file, adjusted=True)["N"]
    except UnmappedError:
        values = None
    bases = {b["code"]: b["formule"] for b in fw.bases_seuil}

    def base(code: str) -> str:
        if values is None or code not in bases:
            return "—"
        return reports.amount(evaluate(bases[code], values) or Decimal(0))

    s = get_settings()
    return {
        "entite": db.get(AuditableEntity, file.entity_id).nom,
        "exercice": str(file.exercice),
        "date_cloture": file.date_fin.strftime("%d/%m/%Y"),
        "referentiel": fw.libelle,
        "total_bilan": base("total_bilan"),
        "capitaux_propres": base("capitaux_propres"),
        "resultat": base("resultat"),
        "devise": file.devise,
        "fondement": o.fondement or "",
        "observations": o.observations or "",
        "conventions": reports.conventions_text(o.conventions),
        "signataire": signer or "",
        "cabinet": s.nom_cabinet,
        "lieu": o.lieu or "",
        "date": (o.emis_le or o.signe_le or dt.datetime.now(dt.UTC)).strftime("%d/%m/%Y"),
    }


def render(db: Session, file: AuditFile, o: AuditOpinion, code: str, fmt: str) -> bytes:
    t = db.scalar(
        select(ReportTemplate).where(
            ReportTemplate.code == code, ReportTemplate.deleted_at.is_(None)
        )
    )
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle introuvable")
    signer = _users(db, o.signe_par)[0]
    title = t.nom + (f" – exercice {file.exercice}")
    if o.statut != "emis":
        title = f"PROJET – {title}"
    return documents.render(fmt, title, reports.blocks(t, o, context(db, file, o, signer)))


@router.get("/audit-files/{file_id}/reports/{code}")
def report(
    file_id: uuid.UUID,
    code: str,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    file, _ = get_file(db, file_id, user)
    o = get_opinion(db, file)
    if o is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Opinion à rédiger")
    content = render(db, file, o, code, format)
    record_event(
        db, "export", object_type="AuditFile", object_id=file.id, details={"rapport": code}
    )
    db.commit()
    return Response(
        content,
        media_type=MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{code}_{file.exercice}.{format}"'},
    )
