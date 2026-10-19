"""Justification de chaque compte de bilan d'une clôture (RCO-09).

Statut : justifié (montant justifié égal au solde révisé et pièce jointe), sans pièce,
écart, non justifié. Un compte non justifié reste signalé jusqu'à sa revue par
l'expert-comptable ou le superviseur, revue qui vaut pour le solde revu.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.pieces import _files
from app.api.portfolio import can_manage_client
from app.cabinet.files import file_out, save_upload
from app.config import get_settings
from app.models.portfolio import AccountJustification, Client, Closing
from app.models.revision import AuditFile
from app.models.user import User
from app.revision.mapping import assignments

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)


class JustificationIn(BaseModel):
    montant_justifie: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    commentaire: str | None = Field(default=None, max_length=4000)


class ReviewIn(BaseModel):
    commentaire: str | None = Field(default=None, max_length=4000)


def _client(db: Session, file: AuditFile) -> Client:
    closing = db.scalar(
        select(Closing).where(Closing.audit_file_id == file.id, Closing.deleted_at.is_(None))
    )
    if closing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier qui n'est pas une clôture client")
    return db.get(Client, closing.client_id)


def _rows(db: Session, file: AuditFile) -> dict[str, AccountJustification]:
    return {
        j.compte: j
        for j in db.scalars(
            select(AccountJustification).where(
                AccountJustification.audit_file_id == file.id,
                AccountJustification.deleted_at.is_(None),
            )
        )
    }


def build(db: Session, file: AuditFile) -> dict[str, Any]:
    classes = get_settings().classes_bilan
    balances = {
        a.compte: (a.libelle, a.soldes.get("N", ZERO))
        for a in assignments(db, file, adjusted=True)
        if a.compte[0] in classes and "N" in a.soldes
    }
    rows = _rows(db, file)
    files = _files(db, "justification", [j.id for j in rows.values()])
    out = []
    for compte, (libelle, solde) in sorted(balances.items()):
        j = rows.get(compte)
        attached = files.get(j.id, []) if j else []
        justified = j.montant_justifie if j else None
        if justified is None:
            statut = "non_justifie"
        elif justified != solde:
            statut = "ecart"
        elif not attached:
            statut = "sans_piece"
        else:
            statut = "justifie"
        reviewed = j is not None and j.revue_le is not None and j.solde_revu == solde
        out.append(
            {
                "compte": compte,
                "libelle": libelle,
                "solde": str(solde),
                "montant_justifie": str(justified) if justified is not None else None,
                "ecart": str(solde - justified) if justified is not None else None,
                "commentaire": j.commentaire if j else None,
                "statut": statut,
                "fichiers": [file_out(f) for f in attached],
                "revu": reviewed,
                "commentaire_revue": j.commentaire_revue if reviewed else None,
                "signale": statut != "justifie" and not reviewed,
            }
        )
    return {
        "comptes": out,
        "justifies": sum(r["statut"] == "justifie" for r in out),
        "signales": sum(r["signale"] for r in out),
        "total": len(out),
    }


def _row(db: Session, file: AuditFile, client: Client, compte: str) -> AccountJustification:
    row = _rows(db, file).get(compte)
    if row is None:
        row = AccountJustification(client_id=client.id, audit_file_id=file.id, compte=compte)
        db.add(row)
        db.flush()
    return row


def _bilan_account(db: Session, file: AuditFile, compte: str) -> None:
    if compte not in {r["compte"] for r in build(db, file)["comptes"]}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte de bilan absent de la balance N")


@router.get("/audit-files/{file_id}/justifications")
def read_justifications(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    _client(db, file)
    return build(db, file)


@router.put("/audit-files/{file_id}/justifications/{compte}")
def justify(
    file_id: uuid.UUID, compte: str, body: JustificationIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    client = _client(db, file)
    _bilan_account(db, file, compte)
    row = _row(db, file, client, compte)
    row.montant_justifie, row.commentaire = body.montant_justifie, body.commentaire
    db.commit()
    return build(db, file)


@router.post("/audit-files/{file_id}/justifications/{compte}/files", status_code=201)
def attach(
    file_id: uuid.UUID, compte: str, file: UploadFile, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    audit_file, engagement = get_file(db, file_id, user)
    require_work(audit_file, engagement, user)
    client = _client(db, audit_file)
    _bilan_account(db, audit_file, compte)
    row = _row(db, audit_file, client, compte)
    save_upload(db, client.id, "justification", row.id, file)
    db.commit()
    return build(db, audit_file)


def _reviewer(client: Client, user: User) -> bool:
    return can_manage_client(client, user) or client.superviseur_id == user.id


@router.post("/audit-files/{file_id}/justifications/{compte}/review")
def review(
    file_id: uuid.UUID, compte: str, body: ReviewIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Revue d'un compte par l'expert-comptable ou le superviseur : lève le signalement pour
    le solde revu ; un compte non justifié exige un commentaire."""
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    client = _client(db, file)
    if not _reviewer(client, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Revue : expert-comptable ou superviseur")
    current = next((r for r in build(db, file)["comptes"] if r["compte"] == compte), None)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte de bilan absent de la balance N")
    if current["statut"] != "justifie" and not (body.commentaire or "").strip():
        raise HTTPException(422, "Commentaire obligatoire pour la revue d'un compte non justifié")
    row = _row(db, file, client, compte)
    row.revue_le, row.revue_par = dt.datetime.now(dt.UTC), user.id
    row.solde_revu, row.commentaire_revue = Decimal(current["solde"]), body.commentaire
    db.commit()
    return build(db, file)
