"""Pièces demandées au client (RCO-04) : liste, envoi par le portail, dépôt, relances."""

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, user_from_request
from app.api.portfolio import can_manage_client, get_client
from app.audit.listeners import record_event
from app.cabinet.files import file_out, save_upload
from app.cabinet.pieces import remind, standard_pieces, status_of
from app.models.portfolio import Client, ClientFile, Closing, PieceRequest
from app.models.user import User
from app.notify import notify
from app.security.roles import Perm, Role, has_permission
from app.storage import get_storage

router = APIRouter(tags=["Portefeuille (Module 6)"])


class PieceIn(BaseModel):
    libelle: str = Field(min_length=2, max_length=300)
    categorie: str = Field(default="autre", min_length=2, max_length=40)
    date_limite: dt.date


class StandardIn(BaseModel):
    date_limite: dt.date


class PieceUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=2, max_length=300)
    date_limite: dt.date | None = None
    recue: bool | None = None
    commentaire: str | None = Field(default=None, max_length=2000)


def _files(db: Session, objet: str, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ClientFile]]:
    out: dict[uuid.UUID, list[ClientFile]] = {i: [] for i in ids}
    for f in db.scalars(
        select(ClientFile)
        .where(
            ClientFile.objet == objet, ClientFile.objet_id.in_(ids), ClientFile.deleted_at.is_(None)
        )
        .order_by(ClientFile.created_at)
    ):
        out[f.objet_id].append(f)
    return out


def piece_out(p: PieceRequest, files: list[ClientFile]) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "libelle": p.libelle,
        "categorie": p.categorie,
        "date_limite": p.date_limite.isoformat(),
        "envoyee_le": p.envoyee_le.isoformat() if p.envoyee_le else None,
        "recue_le": p.recue_le.isoformat() if p.recue_le else None,
        "commentaire": p.commentaire,
        "relances": p.relances or [],
        "statut": status_of(p),
        "fichiers": [file_out(f) for f in files],
    }


def _closing(db: Session, closing_id: uuid.UUID, user: User) -> tuple[Closing, Client]:
    closing = db.get(Closing, closing_id)
    if closing is None or closing.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clôture introuvable")
    return closing, get_client(db, closing.client_id, user)


def _require_team(client: Client, user: User) -> None:
    if not (can_manage_client(client, user) or has_permission(user.role, Perm.REVISION_WORK)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'équipe du dossier")


def _pieces(db: Session, closing: Closing) -> list[PieceRequest]:
    return list(
        db.scalars(
            select(PieceRequest)
            .where(PieceRequest.closing_id == closing.id, PieceRequest.deleted_at.is_(None))
            .order_by(PieceRequest.date_limite, PieceRequest.libelle)
        )
    )


def listing(db: Session, closing: Closing) -> dict[str, Any]:
    pieces = _pieces(db, closing)
    files = _files(db, "piece", [p.id for p in pieces])
    items = [piece_out(p, files[p.id]) for p in pieces]
    counts = {
        s: sum(i["statut"] == s for i in items)
        for s in ("a_envoyer", "demandee", "manquante", "recue")
    }
    return {"pieces": items, "totaux": counts}


def _get_piece(db: Session, piece_id: uuid.UUID) -> PieceRequest:
    piece = db.get(PieceRequest, piece_id)
    if piece is None or piece.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pièce introuvable")
    return piece


@router.get("/closings/{closing_id}/pieces")
def list_pieces(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, _ = _closing(db, closing_id, user)
    return listing(db, closing)


@router.post("/closings/{closing_id}/pieces", status_code=status.HTTP_201_CREATED)
def add_piece(
    closing_id: uuid.UUID, body: PieceIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    _require_team(client, user)
    db.add(
        PieceRequest(closing_id=closing.id, client_id=client.id, relances=[], **body.model_dump())
    )
    db.commit()
    return listing(db, closing)


@router.post("/closings/{closing_id}/pieces/standard", status_code=status.HTTP_201_CREATED)
def add_standard(
    closing_id: uuid.UUID, body: StandardIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Reprend la liste type des pièces selon la taille du dossier, sans doublon."""
    closing, client = _closing(db, closing_id, user)
    _require_team(client, user)
    known = {p.libelle for p in _pieces(db, closing)}
    for item in standard_pieces():
        if client.taille in item["tailles"] and item["libelle"] not in known:
            db.add(
                PieceRequest(
                    closing_id=closing.id, client_id=client.id, libelle=item["libelle"],
                    categorie=item["categorie"], date_limite=body.date_limite, relances=[],
                )
            )  # fmt: skip
    db.commit()
    return listing(db, closing)


@router.patch("/pieces/{piece_id}")
def update_piece(
    piece_id: uuid.UUID, body: PieceUpdate, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Reçue hors portail, ou rouverte avec un motif (pièce incomplète ou illisible)."""
    piece = _get_piece(db, piece_id)
    closing, client = _closing(db, piece.closing_id, user)
    _require_team(client, user)
    data = body.model_dump(exclude_unset=True)
    if data.get("recue") is False and not data.get("commentaire"):
        raise HTTPException(422, "Motif obligatoire pour rouvrir une pièce")
    if "recue" in data:
        piece.recue_le = dt.date.today() if data.pop("recue") else None
    for key, value in data.items():
        setattr(piece, key, value)
    if body.recue is False and client.contact_id:
        notify(
            db,
            {client.contact_id},
            "piece_rouverte",
            f"{client.raison_sociale} : pièce à compléter",
            f"La pièce « {piece.libelle} » est à compléter : {piece.commentaire}",
            lien="/",
        )
    db.commit()
    return listing(db, closing)


@router.delete("/pieces/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_piece(piece_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    piece = _get_piece(db, piece_id)
    _, client = _closing(db, piece.closing_id, user)
    _require_team(client, user)
    if piece.recue_le:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pièce déjà reçue")
    piece.deleted_at, piece.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/closings/{closing_id}/pieces/send")
def send_pieces(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Envoie au client, par le portail, les pièces non encore envoyées."""
    closing, client = _closing(db, closing_id, user)
    _require_team(client, user)
    if client.contact_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun contact client pour le portail")
    new = [p for p in _pieces(db, closing) if p.envoyee_le is None]
    if not new:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucune pièce à envoyer")
    for p in new:
        p.envoyee_le = dt.date.today()
    lines = "\n".join(f"- {p.libelle} (avant le {p.date_limite:%d/%m/%Y})" for p in new)
    notify(
        db,
        {client.contact_id},
        "pieces_demandees",
        f"{client.raison_sociale} : {len(new)} pièce(s) demandée(s) "
        f"pour la clôture {closing.exercice}",
        f"Votre cabinet vous demande les pièces suivantes :\n{lines}\n"
        "Déposez-les depuis votre portail.",
        lien="/",
    )
    db.commit()
    return listing(db, closing)


@router.post("/closings/{closing_id}/pieces/remind")
def remind_pieces(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    _require_team(client, user)
    waiting = [p for p in _pieces(db, closing) if status_of(p) in ("demandee", "manquante")]
    if not waiting or client.contact_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucune pièce à relancer")
    remind(db, client, waiting, dt.date.today())
    db.commit()
    return listing(db, closing)


# --- Portail du client -----------------------------------------------------------------------


def _portal_pieces(db: Session, user: User) -> list[tuple[PieceRequest, Client, Closing]]:
    if user.role != Role.AUDITE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au portail du client")
    rows = db.execute(
        select(PieceRequest, Client, Closing)
        .join(Client, Client.id == PieceRequest.client_id)
        .join(Closing, Closing.id == PieceRequest.closing_id)
        .where(
            Client.contact_id == user.id,
            Client.deleted_at.is_(None),
            PieceRequest.deleted_at.is_(None),
            PieceRequest.envoyee_le.is_not(None),
        )
        .order_by(PieceRequest.date_limite, PieceRequest.libelle)
    ).all()
    return [tuple(r) for r in rows]  # type: ignore[misc]


@router.get("/portal/pieces")
def portal_pieces(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    rows = _portal_pieces(db, user)
    files = _files(db, "piece", [p.id for p, _, _ in rows])
    return [
        {**piece_out(p, files[p.id]), "client": c.raison_sociale, "exercice": cl.exercice}
        for p, c, cl in rows
    ]


@router.post("/portal/pieces/{piece_id}/files", status_code=status.HTTP_201_CREATED)
def portal_upload(
    piece_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    match = next(((p, c, cl) for p, c, cl in _portal_pieces(db, user) if p.id == piece_id), None)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pièce introuvable")
    piece, client, closing = match
    stored = save_upload(db, client.id, "piece", piece.id, file)
    piece.recue_le = dt.date.today()
    notify(
        db, {client.expert_id, client.collaborateur_id}, "piece_recue",
        f"{client.raison_sociale} : pièce reçue",
        f"Le client a déposé « {stored.nom_fichier} » pour « {piece.libelle} » "
        f"(clôture {closing.exercice}).",
        lien=f"/portefeuille/{client.id}",
    )  # fmt: skip
    db.commit()
    return file_out(stored)


@router.get("/client-files/{file_id}/content")
def download_client_file(file_id: uuid.UUID, request: Request, db: DbSession) -> StreamingResponse:
    f = db.get(ClientFile, file_id)
    if f is None or f.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable")
    user = user_from_request(request, db)
    client = db.get(Client, f.client_id)
    if client.contact_id != user.id:
        get_client(db, client.id, user)
    record_event(db, "download", object_type="ClientFile", object_id=f.id)
    db.commit()
    return StreamingResponse(
        get_storage().open(f.storage_key),
        media_type=f.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{f.nom_fichier.replace(chr(34), "")}"',
            "X-Content-SHA256": f.sha256,
        },
    )
