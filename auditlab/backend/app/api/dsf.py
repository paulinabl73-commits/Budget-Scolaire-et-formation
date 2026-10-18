"""Aide à la préparation de la liasse fiscale et statistique (DSF, REV-25)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession, require
from app.api.mapping import values_or_409
from app.audit.listeners import record_event
from app.models.revision import AccountingFramework, DsfModel, StatementLine
from app.models.universe import AuditableEntity
from app.models.user import User
from app.revision import dsf
from app.revision.formula import PREVIOUS
from app.revision.mapping import file_values
from app.security.roles import Perm

router = APIRouter(tags=["Révision – liasse fiscale"])
Reader = Annotated[User, Depends(require(Perm.REVISION_READ, Perm.FRAMEWORKS_MANAGE))]
Manager = Annotated[User, Depends(require(Perm.FRAMEWORKS_MANAGE))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def model_out(m: DsfModel) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "pays": m.pays,
        "nom": m.nom,
        "version": m.version,
        "referentiel": m.referentiel,
        "actif": m.actif,
        "feuilles": [{"nom": f["nom"], "lignes": len(f["lignes"])} for f in m.contenu["feuilles"]],
    }


def _model(db: Session, model_id: uuid.UUID) -> DsfModel:
    m = db.get(DsfModel, model_id)
    if m is None or m.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle de liasse introuvable")
    return m


def _known_codes(db: Session, referentiel: str) -> set[str]:
    codes = db.scalars(
        select(StatementLine.code)
        .join(AccountingFramework, AccountingFramework.id == StatementLine.framework_id)
        .where(AccountingFramework.code == referentiel)
    )
    return {c for code in codes for c in (code, f"{code}{PREVIOUS}")}


@router.get("/dsf-models")
def list_models(user: Reader, db: DbSession) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(DsfModel).where(DsfModel.deleted_at.is_(None)).order_by(DsfModel.pays, DsfModel.nom)
    )
    return [model_out(m) for m in rows]


@router.post("/dsf-models/import", status_code=status.HTTP_201_CREATED)
def import_model(
    user: Manager,
    db: DbSession,
    file: UploadFile,
    pays: str = Form(..., max_length=10),
    nom: str = Form(..., max_length=200),
    version: str = Form(..., max_length=40),
    referentiel: str = Form("SYSCOHADA", max_length=20),
) -> dict[str, Any]:
    try:
        contenu = dsf.model_from_excel(file.file.read(20 * 1024 * 1024))
        dsf.check(contenu, _known_codes(db, referentiel))
    except dsf.DsfError as exc:
        raise HTTPException(422, str(exc)) from exc
    m = DsfModel(
        pays=pays.upper(), nom=nom, version=version, referentiel=referentiel, contenu=contenu
    )
    db.add(m)
    db.commit()
    return model_out(m)


@router.patch("/dsf-models/{model_id}")
def toggle_model(
    model_id: uuid.UUID, user: Manager, db: DbSession, actif: bool = Query(...)
) -> dict[str, Any]:
    m = _model(db, model_id)
    m.actif = actif
    db.commit()
    return model_out(m)


@router.get("/dsf-models/{model_id}/template")
def export_model(model_id: uuid.UUID, user: Reader, db: DbSession) -> Response:
    m = _model(db, model_id)
    return Response(
        dsf.model_to_excel(m.contenu),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="modele_dsf_{m.pays}.xlsx"'},
    )


def _fill(db: Session, file_id: uuid.UUID, model_id: uuid.UUID, user: User) -> tuple[Any, ...]:
    file, _ = get_file(db, file_id, user)
    values_or_409(db, file)
    m = _model(db, model_id)
    after = file_values(db, file, adjusted=True)
    n = {**after["N"], **{f"{k}{PREVIOUS}": v for k, v in after["N-1"].items()}}
    return file, m, dsf.fill(m.contenu, n, after["N-1"])


@router.get("/audit-files/{file_id}/dsf")
def read_dsf(
    file_id: uuid.UUID, user: CurrentUser, db: DbSession, model_id: uuid.UUID
) -> dict[str, Any]:
    _, m, sheets = _fill(db, file_id, model_id, user)
    return {"modele": model_out(m), "feuilles": sheets}


@router.get("/audit-files/{file_id}/dsf/export")
def export_dsf(
    file_id: uuid.UUID, user: CurrentUser, db: DbSession, model_id: uuid.UUID
) -> Response:
    file, m, sheets = _fill(db, file_id, model_id, user)
    fw = db.get(AccountingFramework, file.framework_id)
    identification = {
        "Dénomination": db.get(AuditableEntity, file.entity_id).nom,
        "Exercice": str(file.exercice),
        "Date de clôture": file.date_fin.strftime("%d/%m/%Y"),
        "Devise": file.devise,
        "Référentiel": f"{fw.code} {fw.version}",
        "Pays": m.pays,
        "Modèle": f"{m.nom} ({m.version})",
    }
    content = dsf.to_excel(
        identification, sheets, f"Liasse fiscale et statistique – exercice {file.exercice}"
    )
    record_event(
        db, "export", object_type="AuditFile", object_id=file.id, details={"dsf": str(m.id)}
    )
    db.commit()
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="dsf_{file.exercice}.xlsx"'},
    )
