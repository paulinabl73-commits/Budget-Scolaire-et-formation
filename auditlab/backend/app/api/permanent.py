"""Dossier permanent du client (RCO-05) et documents expirés (RCO-06)."""

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.pieces import _files, _require_team
from app.api.portfolio import get_client
from app.cabinet.files import file_out, save_upload
from app.models.portfolio import Client, PermanentDocument

router = APIRouter(tags=["Portefeuille (Module 6)"])
CATEGORIES = ("statuts", "rccm", "identifiant_fiscal", "organigramme", "contrat", "bail",
              "emprunt", "credit_bail", "caution", "autre")  # fmt: skip


class DocumentUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=2, max_length=300)
    date_document: dt.date | None = None
    date_validite: dt.date | None = None
    commentaire: str | None = Field(default=None, max_length=2000)


def documents(db: Session, client: Client) -> list[PermanentDocument]:
    return list(
        db.scalars(
            select(PermanentDocument)
            .where(PermanentDocument.client_id == client.id, PermanentDocument.deleted_at.is_(None))
            .order_by(PermanentDocument.categorie, PermanentDocument.libelle)
        )
    )


def listing(db: Session, client: Client) -> list[dict[str, Any]]:
    docs = documents(db, client)
    files = _files(db, "permanent", [d.id for d in docs])
    return [
        {
            "id": str(d.id),
            "categorie": d.categorie,
            "libelle": d.libelle,
            "date_document": d.date_document.isoformat() if d.date_document else None,
            "date_validite": d.date_validite.isoformat() if d.date_validite else None,
            "commentaire": d.commentaire,
            "fichiers": [file_out(f) for f in files[d.id]],
        }
        for d in docs
    ]


def _get(db: Session, doc_id: uuid.UUID, user: Any) -> tuple[PermanentDocument, Client]:
    doc = db.get(PermanentDocument, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable")
    client = get_client(db, doc.client_id, user)
    _require_team(client, user)
    return doc, client


@router.get("/clients/{client_id}/permanent")
def list_documents(client_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return listing(db, get_client(db, client_id, user))


@router.post("/clients/{client_id}/permanent", status_code=status.HTTP_201_CREATED)
def add_document(
    client_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    categorie: Literal[CATEGORIES] = Form(),  # type: ignore[valid-type]
    libelle: str = Form(min_length=2, max_length=300),
    date_document: dt.date | None = Form(default=None),
    date_validite: dt.date | None = Form(default=None),
    commentaire: str | None = Form(default=None, max_length=2000),
    file: UploadFile | None = None,
) -> list[dict[str, Any]]:
    """Ajoute un document, avec son fichier le cas échéant."""
    client = get_client(db, client_id, user)
    _require_team(client, user)
    doc = PermanentDocument(
        client_id=client.id, categorie=categorie, libelle=libelle, date_document=date_document,
        date_validite=date_validite, commentaire=commentaire,
    )  # fmt: skip
    db.add(doc)
    db.flush()
    if file is not None:
        save_upload(db, client.id, "permanent", doc.id, file)
    db.commit()
    return listing(db, client)


@router.post("/permanent/{doc_id}/files", status_code=status.HTTP_201_CREATED)
def add_file(
    doc_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DbSession
) -> list[dict[str, Any]]:
    doc, client = _get(db, doc_id, user)
    save_upload(db, client.id, "permanent", doc.id, file)
    db.commit()
    return listing(db, client)


@router.patch("/permanent/{doc_id}")
def update_document(
    doc_id: uuid.UUID, body: DocumentUpdate, user: CurrentUser, db: DbSession
) -> list[dict[str, Any]]:
    doc, client = _get(db, doc_id, user)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(doc, key, value)
    db.commit()
    return listing(db, client)


@router.delete("/permanent/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    doc, _ = _get(db, doc_id, user)
    doc.deleted_at, doc.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()
