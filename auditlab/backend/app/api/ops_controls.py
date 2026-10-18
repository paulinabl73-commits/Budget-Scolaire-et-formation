"""Contrôles des organismes de prévoyance sociale (CIP-02 à CIP-05) depuis le dossier."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.operations import REGISTRY
from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import ensure_open
from app.models.data import Dataset
from app.models.revision import AccountingFramework, AuditFile
from app.revision.ops import CONTROLS, Context, OpsControl

router = APIRouter(tags=["Révision – contrôles des organismes de prévoyance sociale"])


class OpsLaunchIn(BaseModel):
    table_id: uuid.UUID
    seconde_table_id: uuid.UUID | None = None
    parametres: dict[str, Any] = {}


def cipres(db: Session, file: AuditFile) -> AccountingFramework:
    fw = db.get(AccountingFramework, file.framework_id)
    if fw.code != "CIPRES":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Contrôles réservés aux dossiers tenus selon le plan CIPRES"
        )
    return fw


def _resolve(
    db: Session, file: AuditFile, fw: AccountingFramework, c: OpsControl
) -> tuple[Context, dict[str, Any]]:
    ctx = Context(db, file, fw)
    return ctx, {**c.regulatory(ctx), **c.fixed(file)}


def _runs(db: Session, file: AuditFile, c: OpsControl) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Dataset)
        .where(
            Dataset.engagement_id == file.engagement_id,
            Dataset.operation == c.operation,
            Dataset.deleted_at.is_(None),
        )
        .order_by(Dataset.created_at.desc())
    )
    return [
        {
            "id": str(d.id),
            "nom": d.nom,
            "statut": d.statut,
            "nb_lignes": d.nb_lignes,
            "resultat": d.resultat,
            "cree_le": d.created_at.isoformat(),
        }
        for d in rows
        if d.definition.get("dossier") == str(file.id)
    ][:5]


@router.get("/audit-files/{file_id}/ops-controls")
def list_controls(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    fw = cipres(db, file)
    out = []
    for c in CONTROLS.values():
        ctx, params = _resolve(db, file, fw, c)
        out.append(
            {
                "code": c.code,
                "exigence": c.exigence,
                "libelle": c.libelle,
                "operation": c.operation,
                "tables": list(c.tables),
                "parametres": [
                    p for p in REGISTRY[c.operation].describe()["params"] if p["nom"] not in params
                ],
                "reglementaires": ctx.used,
                "manquants": ctx.missing,
                "executions": _runs(db, file, c),
            }
        )
    return {"pays": file.pays, "exercice": file.exercice, "controles": out}


@router.get("/audit-files/{file_id}/ops-indicators")
def read_indicators(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """CIP-06 et CIP-07 : indicateurs calculés sur les soldes révisés du dossier."""
    from app.revision.ops_indicators import NotMapped, indicators

    file, _ = get_file(db, file_id, user)
    cipres(db, file)
    try:
        return indicators(db, file)
    except NotMapped as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/audit-files/{file_id}/ops-controls/{code}", status_code=status.HTTP_202_ACCEPTED)
def launch_control(
    file_id: uuid.UUID, code: str, body: OpsLaunchIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    from app.api.analyses import AnalysisIn, launch

    file, engagement = get_file(db, file_id, user)
    ensure_open(engagement)
    if file.statut != "ouvert":
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier clos")
    fw = cipres(db, file)
    c = CONTROLS.get(code)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrôle inconnu")
    ctx, params = _resolve(db, file, fw, c)
    if ctx.missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "Paramètres réglementaires manquants pour "
                f"{file.pays or 'le pays du dossier'} et l'exercice {file.exercice} : "
                + ", ".join(ctx.missing),
                "points": ctx.missing,
            },
        )
    imposed = set(body.parametres) & set(params)
    if imposed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Valeur imposée par le référentiel : {', '.join(sorted(imposed))}",
        )
    ds = launch(
        body.table_id,
        AnalysisIn(
            operation=c.operation,
            parametres={**body.parametres, **params},
            nom=f"{c.libelle} – exercice {file.exercice}",
            seconde_table_id=body.seconde_table_id,
        ),
        user,
        db,
    )
    dataset = db.get(Dataset, ds.id)
    dataset.definition = {
        **dataset.definition,
        "dossier": str(file.id),
        "controle": c.exigence,
        "reglementaires": ctx.used,
    }
    db.commit()
    return {"dataset_id": str(ds.id)}
