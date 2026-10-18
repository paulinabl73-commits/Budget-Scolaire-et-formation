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


# --- Signature et émission (REV-28) -----------------------------------------------------------


def _fingerprint(db: Session, file: AuditFile, o: AuditOpinion) -> str:
    """Empreinte du contenu signé : sections rendues du rapport et du rapport spécial."""
    import hashlib
    import json

    signer = _users(db, o.signe_par)[0]
    content = []
    for code in ("opinion", "conventions"):
        t = db.scalar(
            select(ReportTemplate).where(
                ReportTemplate.code == code, ReportTemplate.deleted_at.is_(None)
            )
        )
        content.append(reports.blocks(t, o, context(db, file, o, signer)))
    return hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def can_sign(engagement: Any, user: User) -> bool:
    """L'associé signataire membre de la mission, ou le chef de mission."""
    from app.api.audit_files import can_direct
    from app.api.mission_access import mission_role
    from app.security.roles import has_permission

    signer = (
        has_permission(user.role, Perm.OPINION_SIGN) and mission_role(engagement, user) is not None
    )
    return signer or can_direct(engagement, user)


def blocking_points(db: Session, file: AuditFile, user: User) -> list[str]:
    from app.api.adjustments import file_adjustments
    from app.revision import statements

    points = []
    try:
        if not all(c["ok"] for c in statements.build(db, file)["controles"]):
            points.append("Contrôles de cohérence des états en écart")
    except UnmappedError as exc:
        points.append(str(exc))
    if not (file.conclusion_synthese or "").strip():
        points.append("Conclusion de la note de synthèse non rédigée")
    if any(a.statut == "proposee" for a in file_adjustments(db, file.id)):
        points.append("Écritures d'ajustement en attente de la décision de l'entité")
    return points


def _signable(db: Session, file_id: uuid.UUID, user: User) -> tuple[AuditFile, AuditOpinion]:
    file, engagement = get_file(db, file_id, user)
    if not can_sign(engagement, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé à l'associé signataire ou au chef de mission"
        )
    o = get_opinion(db, file)
    if o is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Opinion à rédiger")
    if o.statut == "emis" or file.statut != "ouvert":
        raise HTTPException(status.HTTP_409_CONFLICT, "Rapport émis : dossier verrouillé")
    return file, o


@router.post("/audit-files/{file_id}/opinion/sign")
def sign(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, o = _signable(db, file_id, user)
    if o.statut != "brouillon":
        raise HTTPException(status.HTTP_409_CONFLICT, "Opinion déjà signée")
    points = blocking_points(db, file, user)
    if points:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": "Signature impossible", "points": points}
        )
    o.statut, o.signe_par, o.signe_le = "signe", user.id, dt.datetime.now(dt.UTC)
    o.empreinte = _fingerprint(db, file, o)
    record_event(
        db,
        "signature",
        object_type="AuditOpinion",
        object_id=o.id,
        details={"empreinte": o.empreinte, "type_opinion": o.type_opinion},
    )
    db.commit()
    return opinion_out(db, file, user, o)


@router.post("/audit-files/{file_id}/opinion/unsign")
def unsign(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, o = _signable(db, file_id, user)
    if o.statut != "signe":
        raise HTTPException(status.HTTP_409_CONFLICT, "Opinion non signée")
    o.statut, o.signe_par, o.signe_le, o.empreinte = "brouillon", None, None, None
    db.commit()
    return opinion_out(db, file, user, o)


@router.post("/audit-files/{file_id}/opinion/emit")
def emit(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Émet le rapport signé : archive le document définitif avec son empreinte et verrouille
    le dossier (plus aucune écriture, AUD-22)."""
    import hashlib
    import io

    from app.storage import get_storage

    file, o = _signable(db, file_id, user)
    if o.statut != "signe":
        raise HTTPException(status.HTTP_409_CONFLICT, "Signature requise avant émission")
    if _fingerprint(db, file, o) != o.empreinte:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Le contenu du rapport a changé depuis la signature : signez à nouveau",
        )
    o.statut, o.emis_par, o.emis_le = "emis", user.id, dt.datetime.now(dt.UTC)
    signer = _users(db, o.signe_par)[0]
    blocks: list[dict[str, Any]] = []
    for code in ("opinion", "conventions"):
        t = db.scalar(
            select(ReportTemplate).where(
                ReportTemplate.code == code, ReportTemplate.deleted_at.is_(None)
            )
        )
        if blocks:
            blocks.append({"saut": True})
        blocks += [
            {"titre": t.nom, "niveau": 1},
            *reports.blocks(t, o, context(db, file, o, signer)),
        ]
    content = documents.to_pdf(
        f"Rapports du commissaire aux comptes – exercice {file.exercice}", blocks
    )
    stored = get_storage().put(
        f"revision/{file.id}/rapport_emis_{uuid.uuid4()}.pdf", io.BytesIO(content)
    )
    o.archive_key, o.archive_sha256 = stored.key, hashlib.sha256(content).hexdigest()
    file.statut = "archive"
    record_event(
        db,
        "emission",
        object_type="AuditOpinion",
        object_id=o.id,
        details={"archive_sha256": o.archive_sha256},
    )
    db.commit()
    return opinion_out(db, file, user, o)


@router.get("/audit-files/{file_id}/opinion/archive")
def archive(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    from app.storage import get_storage

    file, _ = get_file(db, file_id, user)
    o = get_opinion(db, file)
    if o is None or o.archive_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun rapport émis")
    content = b"".join(get_storage().open(o.archive_key))
    record_event(db, "download", object_type="AuditOpinion", object_id=o.id)
    db.commit()
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="rapport_emis_{file.exercice}.pdf"'},
    )
