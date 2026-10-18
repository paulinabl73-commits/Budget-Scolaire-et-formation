"""Référentiels comptables (REV-01) et cadres normatifs (REV-03)."""

import hashlib
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import DbSession, require
from app.models.revision import (
    AccountingFramework,
    FrameworkAccount,
    NormativeFramework,
    RegulatoryParameter,
    StatementLine,
)
from app.models.user import User
from app.revision.frameworks import FrameworkError, load_framework, read_excel, to_excel
from app.security.roles import Perm

router = APIRouter(tags=["Référentiels"])
Reader = Annotated[User, Depends(require(Perm.REVISION_READ, Perm.FRAMEWORKS_MANAGE))]
Manager = Annotated[User, Depends(require(Perm.FRAMEWORKS_MANAGE))]
MAX_BYTES = 20 * 1024 * 1024


class FrameworkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    version: str
    libelle: str
    pays: str
    date_effet: date
    actif: bool
    source: str | None
    ratios: list[dict[str, Any]]
    bases_seuil: list[dict[str, Any]]
    regles: list[dict[str, Any]]
    branches: list[dict[str, Any]]
    nb_comptes: int = 0
    nb_postes: int = 0


def framework_out(db: DbSession, fw: AccountingFramework) -> FrameworkOut:
    out = FrameworkOut.model_validate(fw)
    out.nb_comptes = db.scalar(select(func.count()).where(FrameworkAccount.framework_id == fw.id))
    out.nb_postes = db.scalar(select(func.count()).where(StatementLine.framework_id == fw.id))
    return out


def get_framework(db: DbSession, framework_id: uuid.UUID) -> AccountingFramework:
    fw = db.scalar(
        select(AccountingFramework).where(
            AccountingFramework.id == framework_id, AccountingFramework.deleted_at.is_(None)
        )
    )
    if fw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Référentiel introuvable")
    return fw


@router.get("/frameworks", response_model=list[FrameworkOut])
def list_frameworks(user: Reader, db: DbSession, code: str | None = None) -> list[FrameworkOut]:
    query = select(AccountingFramework).where(AccountingFramework.deleted_at.is_(None))
    if code:
        query = query.where(AccountingFramework.code == code)
    rows = db.scalars(
        query.order_by(AccountingFramework.code, AccountingFramework.date_effet.desc())
    )
    return [framework_out(db, f) for f in rows]


@router.get("/frameworks/{framework_id}")
def read_framework(framework_id: uuid.UUID, user: Reader, db: DbSession) -> dict[str, Any]:
    fw = get_framework(db, framework_id)
    accounts = db.scalars(
        select(FrameworkAccount)
        .where(FrameworkAccount.framework_id == fw.id)
        .order_by(FrameworkAccount.numero)
    )
    lines = db.scalars(
        select(StatementLine)
        .where(StatementLine.framework_id == fw.id)
        .order_by(StatementLine.ordre)
    )
    params = db.scalars(
        select(RegulatoryParameter)
        .where(RegulatoryParameter.framework_id == fw.id, RegulatoryParameter.deleted_at.is_(None))
        .order_by(RegulatoryParameter.code)
    )
    return {
        **framework_out(db, fw).model_dump(mode="json"),
        "comptes": [
            {"numero": a.numero, "libelle": a.libelle, "classe": a.classe, "branche": a.branche}
            for a in accounts
        ],
        "postes": [
            {
                "etat": p.etat,
                "code": p.code,
                "libelle": p.libelle,
                "nature": p.nature,
                "racines": p.racines,
                "formule": p.formule,
                "niveau": p.niveau,
            }
            for p in lines
        ],  # fmt: skip
        "parametres": [
            {
                "code": p.code,
                "libelle": p.libelle,
                "valeur": str(p.valeur),
                "unite": p.unite,
                "pays": p.pays,
                "exercice": p.exercice,
                "branche": p.branche,
            }
            for p in params
        ],  # fmt: skip
    }


@router.post("/frameworks/import", response_model=FrameworkOut, status_code=status.HTTP_201_CREATED)
def import_framework(file: UploadFile, user: Manager, db: DbSession) -> FrameworkOut:
    """Nouvelle version depuis un classeur Excel ; les dossiers ouverts gardent leur version."""
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Classeur trop volumineux (20 Mo au plus)")
    try:
        fw = load_framework(db, read_excel(content), hashlib.sha256(content).hexdigest())
    except FrameworkError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return framework_out(db, fw)


@router.get("/frameworks/{framework_id}/export")
def export_framework(framework_id: uuid.UUID, user: Reader, db: DbSession) -> Response:
    """Classeur du référentiel, à modifier puis réimporter comme nouvelle version."""
    fw = get_framework(db, framework_id)
    name = f"referentiel_{fw.code}_{fw.version}_{fw.pays}.xlsx".replace(" ", "_")
    return Response(
        to_excel(db, fw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class FrameworkUpdate(BaseModel):
    actif: bool


@router.patch("/frameworks/{framework_id}", response_model=FrameworkOut)
def update_framework(
    framework_id: uuid.UUID, body: FrameworkUpdate, user: Manager, db: DbSession
) -> FrameworkOut:
    """Seule l'activation change : une version désactivée n'est plus proposée aux nouveaux
    dossiers, les dossiers existants la conservent."""
    fw = get_framework(db, framework_id)
    fw.actif = body.actif
    db.commit()
    return framework_out(db, fw)


# --- REV-03 : cadres normatifs -------------------------------------------------------------


class NormativeIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    libelle: str = Field(min_length=1, max_length=300)
    description: str | None = None
    actif: bool = True


class NormativeOut(NormativeIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


@router.get("/normative-frameworks", response_model=list[NormativeOut])
def list_normatives(user: Reader, db: DbSession) -> list[NormativeFramework]:
    return list(
        db.scalars(
            select(NormativeFramework)
            .where(NormativeFramework.deleted_at.is_(None))
            .order_by(NormativeFramework.libelle)
        )
    )


@router.post(
    "/normative-frameworks", response_model=NormativeOut, status_code=status.HTTP_201_CREATED
)
def create_normative(body: NormativeIn, user: Manager, db: DbSession) -> NormativeFramework:
    if db.scalar(select(NormativeFramework).where(NormativeFramework.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Code déjà utilisé")
    nf = NormativeFramework(**body.model_dump())
    db.add(nf)
    db.commit()
    return nf


@router.put("/normative-frameworks/{normative_id}", response_model=NormativeOut)
def update_normative(
    normative_id: uuid.UUID, body: NormativeIn, user: Manager, db: DbSession
) -> NormativeFramework:
    nf = db.get(NormativeFramework, normative_id)
    if nf is None or nf.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cadre normatif introuvable")
    for key, value in body.model_dump(exclude={"code"}).items():
        setattr(nf, key, value)
    db.commit()
    return nf


# --- Paramètres réglementaires (CIP-09) ----------------------------------------------------------


class ParameterIn(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    libelle: str = Field(min_length=2, max_length=300)
    valeur: Decimal
    unite: str | None = Field(default=None, max_length=30)
    pays: str | None = Field(default=None, max_length=40)
    exercice: int | None = Field(default=None, ge=1990, le=2100)
    branche: str | None = Field(default=None, max_length=20)


def parameter_out(p: RegulatoryParameter) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "code": p.code,
        "libelle": p.libelle,
        "valeur": str(p.valeur),
        "unite": p.unite,
        "pays": p.pays,
        "exercice": p.exercice,
        "branche": p.branche,
    }


@router.get("/frameworks/{framework_id}/parameters")
def list_parameters(framework_id: uuid.UUID, user: Reader, db: DbSession) -> dict[str, Any]:
    from app.revision.parameters import catalog

    get_framework(db, framework_id)
    rows = db.scalars(
        select(RegulatoryParameter)
        .where(
            RegulatoryParameter.framework_id == framework_id,
            RegulatoryParameter.deleted_at.is_(None),
        )
        .order_by(RegulatoryParameter.code, RegulatoryParameter.pays, RegulatoryParameter.exercice)
    )
    return {"catalogue": catalog(), "parametres": [parameter_out(p) for p in rows]}


@router.post("/frameworks/{framework_id}/parameters", status_code=status.HTTP_201_CREATED)
def create_parameter(
    framework_id: uuid.UUID, body: ParameterIn, user: Manager, db: DbSession
) -> dict[str, Any]:
    fw = get_framework(db, framework_id)
    if body.branche and body.branche not in {b["code"] for b in fw.branches}:
        raise HTTPException(422, "Branche inconnue du référentiel")
    duplicate = db.scalar(
        select(RegulatoryParameter).where(
            RegulatoryParameter.framework_id == fw.id,
            RegulatoryParameter.code == body.code,
            RegulatoryParameter.pays.is_not_distinct_from(body.pays),
            RegulatoryParameter.exercice.is_not_distinct_from(body.exercice),
            RegulatoryParameter.branche.is_not_distinct_from(body.branche),
            RegulatoryParameter.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Paramètre déjà défini pour ce pays, cet exercice et cette branche",
        )
    p = RegulatoryParameter(framework_id=fw.id, **body.model_dump())
    db.add(p)
    db.commit()
    return parameter_out(p)


@router.delete("/regulatory-parameters/{parameter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_parameter(parameter_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    import datetime as dt

    p = db.get(RegulatoryParameter, parameter_id)
    if p is None or p.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paramètre introuvable")
    p.deleted_at, p.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()
