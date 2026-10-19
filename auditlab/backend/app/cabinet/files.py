"""Fichiers des dossiers clients du cabinet (pièces, dossier permanent, justificatifs)."""

import uuid
from pathlib import PurePath

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.attachments import ALLOWED
from app.config import get_settings
from app.models.portfolio import ClientFile
from app.storage import TooLarge, get_storage


def save_upload(
    db: Session, client_id: uuid.UUID, objet: str, objet_id: uuid.UUID, file: UploadFile
) -> ClientFile:
    name = PurePath(file.filename or "fichier").name[:255]
    ext = PurePath(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Format non admis : PDF, Excel, Word, CSV, texte ou image")
    content_type, magics = ALLOWED[ext]
    head = file.file.read(8)
    file.file.seek(0)
    if magics and not any(head.startswith(m) for m in magics):
        raise HTTPException(415, "Le contenu du fichier ne correspond pas à son extension")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    try:
        stored = get_storage().put(
            f"clients/{client_id}/{objet}/{uuid.uuid4()}{ext}", file.file, max_bytes=max_bytes
        )
    except TooLarge as exc:
        raise HTTPException(413, f"Fichier trop volumineux ({max_bytes // 2**20} Mo)") from exc
    row = ClientFile(
        client_id=client_id, objet=objet, objet_id=objet_id, nom_fichier=name,
        content_type=content_type, taille=stored.size, sha256=stored.sha256,
        storage_key=stored.key,
    )  # fmt: skip
    db.add(row)
    db.flush()
    return row


def file_out(f: ClientFile) -> dict:
    return {
        "id": str(f.id),
        "nom_fichier": f.nom_fichier,
        "taille": f.taille,
        "sha256": f.sha256,
        "depose_le": f.created_at.isoformat() if f.created_at else None,
    }
