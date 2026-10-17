"""Pièces jointes des papiers de travail (AUD-15) : jusqu'à 100 Mo, types contrôlés."""

import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import PurePath

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, user_from_request
from app.api.workpapers import get_workpaper, require_preparer
from app.audit.listeners import record_event
from app.config import get_settings
from app.models.workpaper import Attachment, Workpaper
from app.schemas_workpaper import AttachmentOut
from app.signing import sign, verify
from app.storage import TooLarge, get_storage

router = APIRouter(tags=["Pièces jointes"])

# Formats admis et premiers octets attendus (contrôle de cohérence du contenu).
ALLOWED: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK",)),
    ".xls": ("application/vnd.ms-excel", (b"\xd0\xcf\x11\xe0",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK",)),
    ".csv": ("text/csv", ()),
    ".txt": ("text/plain", ()),
    ".png": ("image/png", (b"\x89PNG",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".gif": ("image/gif", (b"GIF8",)),
    ".webp": ("image/webp", (b"RIFF",)),
}


def attachment_out(a: Attachment) -> AttachmentOut:
    expires, sig = sign(f"attachment:{a.id}")
    return AttachmentOut.model_validate(a).model_copy(
        update={"url": f"/api/attachments/{a.id}/content?expires={expires}&sig={sig}"}
    )


def workpaper_attachments(db: Session, workpaper: Workpaper) -> list[Attachment]:
    return list(
        db.scalars(
            select(Attachment)
            .where(Attachment.workpaper_id == workpaper.id, Attachment.deleted_at.is_(None))
            .order_by(Attachment.nom_fichier, Attachment.version.desc())
        )
    )


@router.get("/workpapers/{workpaper_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(
    workpaper_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[AttachmentOut]:
    wp, _ = get_workpaper(db, workpaper_id, user)
    return [attachment_out(a) for a in workpaper_attachments(db, wp)]


@router.post(
    "/workpapers/{workpaper_id}/attachments", response_model=AttachmentOut, status_code=201
)
def upload(
    workpaper_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DbSession
) -> AttachmentOut:
    wp, engagement = get_workpaper(db, workpaper_id, user)
    require_preparer(engagement, user)
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
    key = f"attachments/{engagement.id}/{uuid.uuid4()}{ext}"
    try:
        stored = get_storage().put(key, file.file, max_bytes=max_bytes)
    except TooLarge as exc:
        raise HTTPException(
            413, f"Fichier trop volumineux (maximum {max_bytes // 2**20} Mo)"
        ) from exc
    previous = (
        db.scalar(
            select(func.max(Attachment.version)).where(
                Attachment.workpaper_id == wp.id, Attachment.nom_fichier == name
            )
        )
        or 0
    )
    attachment = Attachment(
        engagement_id=engagement.id,
        workpaper_id=wp.id,
        nom_fichier=name,
        content_type=content_type,
        taille=stored.size,
        sha256=stored.sha256,
        storage_key=stored.key,
        version=previous + 1,
    )
    db.add(attachment)
    db.commit()
    return attachment_out(attachment)


@router.get("/attachments/{attachment_id}/content")
def download(
    attachment_id: uuid.UUID,
    request: Request,
    db: DbSession,
    expires: int | None = None,
    sig: str | None = None,
) -> StreamingResponse:
    """Accès par lien signé (balises <img>) ou par session authentifiée."""
    attachment = db.scalar(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.deleted_at.is_(None))
    )
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pièce jointe introuvable")
    if not (expires and sig and verify(f"attachment:{attachment.id}", expires, sig)):
        user = user_from_request(request, db)
        get_workpaper(db, attachment.workpaper_id, user)
        record_event(db, "download", object_type="Attachment", object_id=attachment.id)
        db.commit()
    disposition = (
        "inline"
        if attachment.content_type.startswith(("image/", "application/pdf"))
        else "attachment"
    )
    filename = attachment.nom_fichier.replace('"', "")
    return StreamingResponse(
        get_storage().open(attachment.storage_key),
        media_type=attachment.content_type or mimetypes.guess_type(filename)[0],
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-Content-SHA256": attachment.sha256,
            "Cache-Control": "private, max-age=600",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    attachment = db.scalar(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.deleted_at.is_(None))
    )
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pièce jointe introuvable")
    _, engagement = get_workpaper(db, attachment.workpaper_id, user)
    require_preparer(engagement, user)
    attachment.deleted_at = datetime.now(UTC)
    attachment.deleted_by = user.id
    db.commit()
