"""Bibliothèque de tests prêts à l'emploi par cycle (DAT-28), publiée par les data analysts.

Un test publié n'est jamais modifié : une nouvelle version est créée en brouillon puis
publiée, et remplace alors la précédente. Une mission reprend un test publié en copiant son
code dans un script (référence et version conservées).
"""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.datasets import require_analyst
from app.api.deps import CurrentUser, DbSession, require
from app.api.mission_access import get_engagement
from app.api.scripts import Entry, ScriptIn, _check, script_out
from app.models.data import Script, ScriptTemplate
from app.models.user import User
from app.scripting.catalog import cycles
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Scripts"])
Reader = Annotated[User, Depends(require(Perm.DATA_READ))]
Publisher = Annotated[User, Depends(require(Perm.DATA_PUBLISH_LIBRARY))]


class TemplateIn(BaseModel):
    reference: str = Field(pattern=r"^[A-Z]{2,5}-\d{2,3}$")
    cycle: str
    nom: str = Field(min_length=3, max_length=200)
    objectif: str | None = Field(default=None, max_length=2000)
    code: str = Field(min_length=1, max_length=200_000)
    colonnes: list[str] = Field(default_factory=list, max_length=50)
    indicateur: str | None = Field(default=None, max_length=100)


class FromLibraryIn(BaseModel):
    modele_id: uuid.UUID
    entrees: list[Entry] = Field(default_factory=list, max_length=20)


def template_out(db: Session, t: ScriptTemplate) -> dict[str, Any]:
    return {
        "id": str(t.id), "reference": t.reference, "cycle": t.cycle, "nom": t.nom,
        "objectif": t.objectif, "code": t.code, "colonnes": t.colonnes,
        "indicateur": t.indicateur, "statut": t.statut, "version": t.version,
        "publie_le": t.publie_le.isoformat() if t.publie_le else None,
        "publie_par": db.get(User, t.publie_par).nom if t.publie_par else None,
    }  # fmt: skip


def _get(db: Session, template_id: uuid.UUID) -> ScriptTemplate:
    t = db.get(ScriptTemplate, template_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test introuvable")
    return t


def _validate(body: TemplateIn) -> None:
    if body.cycle not in cycles():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cycle inconnu")
    try:
        compile(body.code, "script.py", "exec")
    except SyntaxError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Erreur de syntaxe ligne {exc.lineno} : {exc.msg}",
        ) from exc


@router.get("/script-library/cycles")
def list_cycles(user: Reader) -> dict[str, str]:
    return cycles()


@router.get("/script-library")
def list_templates(
    user: Reader, db: DbSession, cycle: str | None = None, tous: bool = Query(False)
) -> list[dict[str, Any]]:
    """Tests publiés ; avec `tous`, les brouillons et les versions retirées (publication)."""
    query = select(ScriptTemplate).where(ScriptTemplate.deleted_at.is_(None))
    if not (tous and has_permission(user.role, Perm.DATA_PUBLISH_LIBRARY)):
        query = query.where(ScriptTemplate.statut == "publie")
    if cycle:
        query = query.where(ScriptTemplate.cycle == cycle)
    rows = db.scalars(query.order_by(ScriptTemplate.reference, ScriptTemplate.version.desc()))
    return [template_out(db, t) for t in rows]


@router.post("/script-library", status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, user: Publisher, db: DbSession) -> dict[str, Any]:
    _validate(body)
    taken = db.scalar(
        select(ScriptTemplate.id).where(
            ScriptTemplate.reference == body.reference, ScriptTemplate.deleted_at.is_(None)
        )
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Référence déjà utilisée")
    t = ScriptTemplate(**body.model_dump(), statut="brouillon", version=1)
    db.add(t)
    db.commit()
    return template_out(db, t)


@router.put("/script-library/{template_id}")
def update_template(
    template_id: uuid.UUID, body: TemplateIn, user: Publisher, db: DbSession
) -> dict[str, Any]:
    t = _get(db, template_id)
    if t.statut != "brouillon":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Test publié : créez une nouvelle version pour le modifier"
        )
    _validate(body)
    if body.reference != t.reference:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Référence non modifiable")
    for key, value in body.model_dump().items():
        setattr(t, key, value)
    db.commit()
    return template_out(db, t)


@router.post("/script-library/{template_id}/versions", status_code=status.HTTP_201_CREATED)
def new_version(template_id: uuid.UUID, user: Publisher, db: DbSession) -> dict[str, Any]:
    t = _get(db, template_id)
    versions = list(
        db.scalars(
            select(ScriptTemplate).where(
                ScriptTemplate.reference == t.reference, ScriptTemplate.deleted_at.is_(None)
            )
        )
    )
    if any(v.statut == "brouillon" for v in versions):
        raise HTTPException(status.HTTP_409_CONFLICT, "Une version est déjà en brouillon")
    draft = ScriptTemplate(
        reference=t.reference, cycle=t.cycle, nom=t.nom, objectif=t.objectif, code=t.code,
        colonnes=t.colonnes, indicateur=t.indicateur, statut="brouillon",
        version=max(v.version for v in versions) + 1,
    )  # fmt: skip
    db.add(draft)
    db.commit()
    return template_out(db, draft)


@router.post("/script-library/{template_id}/publish")
def publish(template_id: uuid.UUID, user: Publisher, db: DbSession) -> dict[str, Any]:
    t = _get(db, template_id)
    if t.statut != "brouillon":
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un brouillon est publié")
    for old in db.scalars(
        select(ScriptTemplate).where(
            ScriptTemplate.reference == t.reference,
            ScriptTemplate.statut == "publie",
            ScriptTemplate.deleted_at.is_(None),
        )
    ):
        old.statut = "remplace"
    t.statut, t.publie_le, t.publie_par = "publie", dt.datetime.now(dt.UTC), user.id
    db.commit()
    return template_out(db, t)


@router.post("/script-library/{template_id}/retire")
def retire(template_id: uuid.UUID, user: Publisher, db: DbSession) -> dict[str, Any]:
    t = _get(db, template_id)
    if t.statut != "publie":
        raise HTTPException(status.HTTP_409_CONFLICT, "Seul un test publié est retiré")
    t.statut = "retire"
    db.commit()
    return template_out(db, t)


@router.post("/engagements/{engagement_id}/scripts/from-library", status_code=201)
def from_library(
    engagement_id: uuid.UUID, body: FromLibraryIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = get_engagement(db, engagement_id, user)
    require_analyst(engagement, user)
    t = _get(db, body.modele_id)
    if t.statut != "publie":
        raise HTTPException(status.HTTP_409_CONFLICT, "Test non publié")
    nom = f"{t.reference} – {t.nom}"[:200]
    spec = ScriptIn(nom=nom, description=t.objectif, code=t.code, entrees=body.entrees)
    s = Script(engagement_id=engagement.id, nom=nom, description=t.objectif, code=t.code,
               entrees=_check(db, engagement, spec), modele_id=t.id,
               modele_version=t.version)  # fmt: skip
    db.add(s)
    db.commit()
    return script_out(db, s)
