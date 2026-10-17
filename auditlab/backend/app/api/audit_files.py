"""Dossiers de révision (Module 5) : création et paramètres (REV-02, REV-03, REV-04)."""

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import can_manage, ensure_open, get_engagement, mission_role
from app.models.engagement import Engagement, MissionRole
from app.models.revision import AccountingFramework, AuditFile, NormativeFramework
from app.models.universe import AuditableEntity
from app.models.user import User
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Révision des comptes"])

MAIN_FRAMEWORKS = ("SYSCOHADA", "CIPRES")


class AuditFileIn(BaseModel):
    exercice: int = Field(ge=1990, le=2100)
    date_debut: dt.date
    date_fin: dt.date
    framework_id: uuid.UUID
    ifrs_framework_id: uuid.UUID | None = None
    normative_id: uuid.UUID | None = None
    devise: str = Field(default="XOF", pattern="^[A-Z]{3}$")
    entity_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _dates(self) -> "AuditFileIn":
        if self.date_fin <= self.date_debut:
            raise ValueError("La fin de l'exercice doit suivre son début")
        return self


class AuditFileUpdate(BaseModel):
    ifrs_framework_id: uuid.UUID | None = None
    normative_id: uuid.UUID | None = None


class AuditFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    entity_id: uuid.UUID
    exercice: int
    date_debut: dt.date
    date_fin: dt.date
    framework_id: uuid.UUID
    ifrs_framework_id: uuid.UUID | None
    normative_id: uuid.UUID | None
    devise: str
    precedent_id: uuid.UUID | None
    statut: str
    base_seuil: str | None
    montant_base: Decimal | None
    pct_seuil: Decimal | None
    seuil_signification: Decimal | None
    pct_planification: Decimal | None
    seuil_planification: Decimal | None
    pct_insignifiant: Decimal | None
    seuil_insignifiant: Decimal | None
    justification_seuil: str | None
    seuil_variation_pct: Decimal
    # Calculés
    entite: str | None = None
    referentiel: str | None = None
    referentiel_ifrs: str | None = None
    cadre_normatif: str | None = None
    precedent_exercice: int | None = None
    peut_travailler: bool = False
    peut_gerer: bool = False


def can_work(engagement: Engagement, user: User) -> bool:
    return has_permission(user.role, Perm.REVISION_WORK) and mission_role(engagement, user) in (
        MissionRole.CHEF,
        MissionRole.AUDITEUR,
    )


def can_direct(engagement: Engagement, user: User) -> bool:
    return has_permission(user.role, Perm.REVISION_MANAGE) and can_manage(engagement, user)


def get_file(db: Session, file_id: uuid.UUID, user: User) -> tuple[AuditFile, Engagement]:
    file = db.scalar(
        select(AuditFile).where(AuditFile.id == file_id, AuditFile.deleted_at.is_(None))
    )
    if file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier de révision introuvable")
    engagement = get_engagement(db, file.engagement_id, user)
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    return file, engagement


def require_work(file: AuditFile, engagement: Engagement, user: User) -> None:
    ensure_open(engagement)
    if file.statut != "ouvert":
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier clos")
    if not (can_work(engagement, user) or can_direct(engagement, user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'équipe de la mission")


def require_direct(file: AuditFile, engagement: Engagement, user: User) -> None:
    ensure_open(engagement)
    if file.statut != "ouvert":
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier clos")
    if not can_direct(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de mission")


def file_out(db: Session, f: AuditFile, engagement: Engagement, user: User) -> AuditFileOut:
    out = AuditFileOut.model_validate(f)
    out.entite = db.get(AuditableEntity, f.entity_id).nom
    fw = db.get(AccountingFramework, f.framework_id)
    out.referentiel = f"{fw.code} {fw.version} ({fw.pays})"
    if f.ifrs_framework_id:
        ifrs = db.get(AccountingFramework, f.ifrs_framework_id)
        out.referentiel_ifrs = f"{ifrs.code} {ifrs.version}"
    if f.normative_id:
        out.cadre_normatif = db.get(NormativeFramework, f.normative_id).libelle
    if f.precedent_id:
        out.precedent_exercice = db.get(AuditFile, f.precedent_id).exercice
    open_ = f.statut == "ouvert" and engagement.statut != "cloturee"
    out.peut_travailler = open_ and (can_work(engagement, user) or can_direct(engagement, user))
    out.peut_gerer = open_ and can_direct(engagement, user)
    return out


def _check_frameworks(db: Session, framework_id: uuid.UUID, ifrs_id: uuid.UUID | None) -> None:
    fw = db.get(AccountingFramework, framework_id)
    if fw is None or fw.deleted_at or not fw.actif or fw.code not in MAIN_FRAMEWORKS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Référentiel principal : une version active de SYSCOHADA ou de CIPRES",
        )
    if ifrs_id is not None:
        ifrs = db.get(AccountingFramework, ifrs_id)
        if ifrs is None or ifrs.deleted_at or ifrs.code != "IFRS":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Référentiel de restitution : IFRS"
            )


def _check_normative(db: Session, normative_id: uuid.UUID | None) -> None:
    if normative_id is not None:
        nf = db.get(NormativeFramework, normative_id)
        if nf is None or nf.deleted_at or not nf.actif:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cadre normatif inconnu")


@router.get("/engagements/{engagement_id}/audit-files", response_model=list[AuditFileOut])
def list_files(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[AuditFileOut]:
    engagement = get_engagement(db, engagement_id, user)
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    rows = db.scalars(
        select(AuditFile)
        .where(AuditFile.engagement_id == engagement.id, AuditFile.deleted_at.is_(None))
        .order_by(AuditFile.exercice.desc())
    )
    return [file_out(db, f, engagement, user) for f in rows]


@router.post(
    "/engagements/{engagement_id}/audit-files",
    response_model=AuditFileOut,
    status_code=status.HTTP_201_CREATED,
)
def create_file(
    engagement_id: uuid.UUID, body: AuditFileIn, user: CurrentUser, db: DbSession
) -> AuditFileOut:
    engagement = get_engagement(db, engagement_id, user)
    ensure_open(engagement)
    if not can_direct(engagement, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au chef de mission")
    entity_id = body.entity_id or engagement.entity_id
    if entity_id is None or db.get(AuditableEntity, entity_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Entité révisée inconnue (rattachez la mission)"
        )
    _check_frameworks(db, body.framework_id, body.ifrs_framework_id)
    _check_normative(db, body.normative_id)
    duplicate = db.scalar(
        select(AuditFile).where(
            AuditFile.entity_id == entity_id,
            AuditFile.exercice == body.exercice,
            AuditFile.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un dossier existe déjà pour cet exercice")
    # REV-04 : le dossier de l'exercice précédent sert d'exercice N-1.
    previous = db.scalar(
        select(AuditFile).where(
            AuditFile.entity_id == entity_id,
            AuditFile.exercice == body.exercice - 1,
            AuditFile.deleted_at.is_(None),
        )
    )
    file = AuditFile(
        engagement_id=engagement.id,
        entity_id=entity_id,
        precedent_id=previous.id if previous else None,
        **body.model_dump(exclude={"entity_id"}),
    )
    db.add(file)
    db.flush()
    on_create(db, file, previous)
    db.commit()
    return file_out(db, file, engagement, user)


# Reprises depuis le dossier N-1 (balance, affectations) enregistrées par les modules suivants.
ON_CREATE: list = []


def on_create(db: Session, file: AuditFile, previous: AuditFile | None) -> None:
    if previous is not None:
        for hook in ON_CREATE:
            hook(db, file, previous)


@router.get("/audit-files/{file_id}", response_model=AuditFileOut)
def read_file(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AuditFileOut:
    file, engagement = get_file(db, file_id, user)
    return file_out(db, file, engagement, user)


@router.patch("/audit-files/{file_id}", response_model=AuditFileOut)
def update_file(
    file_id: uuid.UUID, body: AuditFileUpdate, user: CurrentUser, db: DbSession
) -> AuditFileOut:
    file, engagement = get_file(db, file_id, user)
    require_direct(file, engagement, user)
    data = body.model_dump(exclude_unset=True)
    if "ifrs_framework_id" in data:
        _check_frameworks(db, file.framework_id, data["ifrs_framework_id"])
    _check_normative(db, data.get("normative_id"))
    for key, value in data.items():
        setattr(file, key, value)
    db.commit()
    return file_out(db, file, engagement, user)
