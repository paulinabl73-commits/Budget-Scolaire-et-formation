"""Modèles de rapport de mission (REP-01) : logo, page de garde, sections et leur ordre,
ordre des constats par criticité. Gérés par le Directeur ou l'administrateur."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require
from app.models.report import REPORT_SECTIONS, MissionReportTemplate
from app.models.user import User
from app.security.roles import Perm
from app.storage import TooLarge, get_storage

router = APIRouter(tags=["Rapports de mission"])
Reader = Annotated[User, Depends(require(Perm.MISSIONS_READ_ALL, Perm.MISSIONS_READ_OWN))]
Manager = Annotated[User, Depends(require(Perm.REPORT_PUBLISH, Perm.SETTINGS_MANAGE))]
LOGOS = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff"}
MAX_LOGO = 2 * 1024 * 1024


class CoverIn(BaseModel):
    organisation: str = Field(default="", max_length=200)
    titre: str = Field(min_length=1, max_length=200)
    sous_titre: str = Field(default="", max_length=300)
    mention: str = Field(default="", max_length=300)


class SectionIn(BaseModel):
    code: Literal["synthese", "contexte", "constats", "plans_action", "annexes"]
    titre: str = Field(min_length=1, max_length=200)
    actif: bool = True


class TemplateIn(BaseModel):
    nom: str = Field(min_length=3, max_length=200)
    page_garde: CoverIn
    sections: list[SectionIn]
    ordre_constats: Literal["criticite_decroissante", "criticite_croissante", "reference"]
    pied_de_page: str | None = Field(default=None, max_length=1000)
    actif: bool = True


def template_out(t: MissionReportTemplate) -> dict[str, Any]:
    return {
        "id": str(t.id), "nom": t.nom, "par_defaut": t.par_defaut, "page_garde": t.page_garde,
        "sections": t.sections, "ordre_constats": t.ordre_constats,
        "pied_de_page": t.pied_de_page, "actif": t.actif, "logo": t.logo_storage_key is not None,
    }  # fmt: skip


def get_template(db: Session, template_id: uuid.UUID) -> MissionReportTemplate:
    t = db.get(MissionReportTemplate, template_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle introuvable")
    return t


def default_template(db: Session) -> MissionReportTemplate | None:
    return db.scalar(
        select(MissionReportTemplate).where(
            MissionReportTemplate.par_defaut.is_(True), MissionReportTemplate.deleted_at.is_(None)
        )
    )


def _check(body: TemplateIn) -> None:
    codes = [s.code for s in body.sections]
    if sorted(codes) != sorted(REPORT_SECTIONS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Chaque section (synthèse, contexte, constats, plans, annexes) figure une fois",
        )
    if not any(s.actif and s.code == "constats" for s in body.sections):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La section des constats est obligatoire"
        )


@router.get("/mission-report-templates")
def list_templates(user: Reader, db: DbSession) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(MissionReportTemplate)
        .where(MissionReportTemplate.deleted_at.is_(None))
        .order_by(MissionReportTemplate.par_defaut.desc(), MissionReportTemplate.nom)
    )
    return [template_out(t) for t in rows]


@router.post("/mission-report-templates", status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, user: Manager, db: DbSession) -> dict[str, Any]:
    _check(body)
    data = body.model_dump()
    t = MissionReportTemplate(**data, par_defaut=default_template(db) is None)
    db.add(t)
    db.commit()
    return template_out(t)


@router.put("/mission-report-templates/{template_id}")
def update_template(
    template_id: uuid.UUID, body: TemplateIn, user: Manager, db: DbSession
) -> dict[str, Any]:
    t = get_template(db, template_id)
    _check(body)
    if t.par_defaut and not body.actif:
        raise HTTPException(status.HTTP_409_CONFLICT, "Le modèle par défaut reste actif")
    for key, value in body.model_dump().items():
        setattr(t, key, value)
    db.commit()
    return template_out(t)


@router.post("/mission-report-templates/{template_id}/default")
def make_default(template_id: uuid.UUID, user: Manager, db: DbSession) -> dict[str, Any]:
    t = get_template(db, template_id)
    if not t.actif:
        raise HTTPException(status.HTTP_409_CONFLICT, "Modèle inactif")
    current = default_template(db)
    if current is not None:
        current.par_defaut = False
    t.par_defaut = True
    db.commit()
    return template_out(t)


@router.delete("/mission-report-templates/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    t = get_template(db, template_id)
    if t.par_defaut:
        raise HTTPException(status.HTTP_409_CONFLICT, "Désignez d'abord un autre modèle par défaut")
    t.deleted_at, t.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.put("/mission-report-templates/{template_id}/logo")
def upload_logo(
    template_id: uuid.UUID, file: UploadFile, user: Manager, db: DbSession
) -> dict[str, Any]:
    t = get_template(db, template_id)
    head = file.file.read(8)
    file.file.seek(0)
    kind = next((k for k, magic in LOGOS.items() if head.startswith(magic)), None)
    if kind is None:
        raise HTTPException(415, "Logo au format PNG ou JPEG")
    key = f"report-logos/{t.id}/{uuid.uuid4()}"
    try:
        stored = get_storage().put(key, file.file, max_bytes=MAX_LOGO)
    except TooLarge as exc:
        raise HTTPException(413, "Logo trop volumineux (2 Mo au plus)") from exc
    t.logo_storage_key, t.logo_type, t.logo_sha256 = stored.key, kind, stored.sha256
    db.commit()
    return template_out(t)


@router.delete("/mission-report-templates/{template_id}/logo")
def delete_logo(template_id: uuid.UUID, user: Manager, db: DbSession) -> dict[str, Any]:
    t = get_template(db, template_id)
    t.logo_storage_key = t.logo_type = t.logo_sha256 = None
    db.commit()
    return template_out(t)


@router.get("/mission-report-templates/{template_id}/logo")
def read_logo(template_id: uuid.UUID, user: Reader, db: DbSession) -> StreamingResponse:
    t = get_template(db, template_id)
    if t.logo_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun logo")
    return StreamingResponse(get_storage().open(t.logo_storage_key), media_type=t.logo_type)
