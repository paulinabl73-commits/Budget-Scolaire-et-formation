"""Notifications (dans l'application et par e-mail)."""

import logging
import smtplib
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from email.message import EmailMessage as MimeMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.notification import EmailMessage, Notification
from app.models.user import User

log = logging.getLogger("auditlab.notify")


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    titre: str,
    message: str,
    lien: str | None = None,
    email: bool = True,
) -> None:
    """Notifie chaque destinataire actif (une fois) ; l'e-mail part par la file d'envoi."""
    ids = {u for u in user_ids if u}
    if not ids:
        return
    users = db.scalars(
        select(User).where(User.id.in_(ids), User.actif.is_(True), User.deleted_at.is_(None))
    )
    base = get_settings().public_url.rstrip("/")
    for user in users:
        db.add(Notification(user_id=user.id, type=kind, titre=titre, message=message, lien=lien))
        if email:
            body = message + (f"\n\n{base}{lien}" if lien else "")
            db.add(
                EmailMessage(
                    destinataire=user.email,
                    sujet=f"[AuditLab] {titre}",
                    corps=body,
                    statut="en_attente",
                    tentatives=0,
                )
            )


def send_pending(db: Session, limit: int = 100) -> int:
    """Envoie les e-mails en attente ; renvoie le nombre d'envois réussis."""
    s = get_settings()
    if not s.smtp_host:
        return 0
    sent = 0
    pending = list(
        db.scalars(
            select(EmailMessage)
            .where(EmailMessage.statut == "en_attente", EmailMessage.tentatives < 5)
            .limit(limit)
        )
    )
    if not pending:
        return 0
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
        if s.smtp_tls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
        for mail in pending:
            msg = MimeMessage()
            msg["From"], msg["To"], msg["Subject"] = s.mail_from, mail.destinataire, mail.sujet
            msg.set_content(mail.corps)
            mail.tentatives += 1
            try:
                smtp.send_message(msg)
            except smtplib.SMTPException as exc:
                mail.erreur = str(exc)
                if mail.tentatives >= 5:
                    mail.statut = "echec"
                continue
            mail.statut = "envoye"
            mail.envoye_le = datetime.now(UTC)
            sent += 1
    db.commit()
    log.info("e-mails envoyés", extra={"status": sent})
    return sent
