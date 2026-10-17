"""Balances, balances auxiliaires et grand livre d'un dossier de révision (REV-05 à REV-07)."""

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.audit_files import ON_CREATE, get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.models.data import Dataset
from app.models.revision import TrialBalance, TrialBalanceLine
from app.revision import controls, currency  # noqa: F401 - étapes REV-06 et REV-07
from app.revision.balances import ImportError_
from app.revision.imports import ImportRequest, carry_over, import_file

router = APIRouter(tags=["Révision des comptes"])
ON_CREATE.append(carry_over)
MAX_BYTES = 200 * 1024 * 1024


class TrialBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    audit_file_id: uuid.UUID
    periode: str
    type: str
    logiciel: str
    nom_fichier: str | None
    sha256: str | None
    statut: str
    anomalies: list[dict[str, Any]]
    avertissements: list[dict[str, Any]]
    totaux: dict[str, Any]
    nb_lignes: int
    dataset_id: uuid.UUID | None
    devise_source: str | None
    cours: Decimal | None
    compte_collectif: str | None
    created_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None


@router.post(
    "/audit-files/{file_id}/imports",
    response_model=TrialBalanceOut,
    status_code=status.HTTP_201_CREATED,
)
def upload(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile,
    periode: str = Form("N"),
    type: str = Form("balance"),  # noqa: A002 - nom du champ de formulaire
    logiciel: str = Form("generique"),
    correspondance: str | None = Form(None),
    compte_collectif: str | None = Form(None),
    devise_source: str | None = Form(None),
    date_cours: dt.date | None = Form(None),
) -> TrialBalance:
    """Importe le fichier, applique les contrôles bloquants et enregistre le résultat, accepté ou
    rejeté avec ses anomalies (201 dans les deux cas)."""
    audit_file, engagement = get_file(db, file_id, user)
    require_work(audit_file, engagement, user)
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (200 Mo au plus)")
    try:
        mapping = json.loads(correspondance) if correspondance else None
        if mapping is not None and not isinstance(mapping, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Correspondance : objet JSON attendu"
        ) from exc
    req = ImportRequest(
        periode=periode,
        type=type,
        logiciel=logiciel,
        correspondance=mapping,
        compte_collectif=compte_collectif or None,
        devise_source=devise_source or None,
        date_cours=date_cours,
    )
    try:
        tb = import_file(db, audit_file, content, file.filename or "fichier", req, user.id)
    except ImportError_ as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return tb


@router.get("/audit-files/{file_id}/imports", response_model=list[TrialBalanceOut])
def list_imports(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[TrialBalance]:
    """Tous les imports, y compris rejetés et remplacés (historique)."""
    audit_file, _ = get_file(db, file_id, user)
    return list(
        db.scalars(
            select(TrialBalance)
            .where(TrialBalance.audit_file_id == audit_file.id)
            .order_by(TrialBalance.created_at.desc())
        )
    )


@router.get("/trial-balances/{tb_id}/lines")
def read_lines(tb_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    tb = db.get(TrialBalance, tb_id)
    if tb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import introuvable")
    get_file(db, tb.audit_file_id, user)
    rows = db.scalars(
        select(TrialBalanceLine)
        .where(TrialBalanceLine.trial_balance_id == tb.id)
        .order_by(TrialBalanceLine.compte)
    )
    keys = (
        "ouverture_debit",
        "ouverture_credit",
        "mouvement_debit",
        "mouvement_credit",
        "solde_debit",
        "solde_credit",
    )
    return [
        {"compte": r.compte, "libelle": r.libelle, **{k: str(getattr(r, k)) for k in keys}}
        for r in rows
    ]


class JournalTestsIn(BaseModel):
    journaux_manuels: str = Field(default="OD", max_length=200)
    pas_montant_rond: Decimal = Field(default=Decimal(100000), gt=0)
    lignes_max_compte: int = Field(default=3, ge=1)
    lignes_max_utilisateur: int = Field(default=5, ge=1)


@router.post("/audit-files/{file_id}/journal-tests", status_code=status.HTTP_202_ACCEPTED)
def journal_tests(
    file_id: uuid.UUID, body: JournalTestsIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """REV-17 : lance les tests d'écritures (Module 2) sur le grand livre N du dossier, clôture
    au dernier jour de l'exercice ; les colonnes absentes du grand livre sont ignorées."""
    from app.api.analyses import AnalysisIn, launch
    from app.revision.imports import active_balance

    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    gl = active_balance(db, file.id, "N", "grand_livre")
    if gl is None or gl.dataset_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun grand livre N accepté")
    columns = {c["nom"] for c in db.get(Dataset, gl.dataset_id).schema}
    params: dict[str, Any] = {
        "champ_date": "date",
        "champ_compte": "compte",
        "champ_debit": "debit",
        "champ_credit": "credit",
        "date_cloture": file.date_fin.isoformat(),
        **body.model_dump(mode="json"),
    }
    for param, column in (
        ("champ_journal", "journal"),
        ("champ_utilisateur", "utilisateur"),
        ("champ_libelle", "libelle"),
        ("champ_date_saisie", "date_saisie"),
    ):
        if column in columns:
            params[param] = column
    ds = launch(
        gl.dataset_id,
        AnalysisIn(
            operation="ecritures_journal",
            parametres=params,
            nom=f"Tests des écritures de journal – exercice {file.exercice}",
        ),
        user,
        db,
    )
    return {"dataset_id": str(ds.id), "statut": ds.statut}
