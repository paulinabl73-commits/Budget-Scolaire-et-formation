"""Notifications dans l'application et file d'envoi des e-mails."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin


class Notification(TrackedMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    titre: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    lien: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lue_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailMessage(TrackedMixin, Base):
    """E-mail en file d'attente ; envoyé par la tâche d'envoi (SMTP configuré)."""

    __tablename__ = "email_messages"

    destinataire: Mapped[str] = mapped_column(String(255))
    sujet: Mapped[str] = mapped_column(String(300))
    corps: Mapped[str] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(20), default="en_attente")  # envoye, echec
    tentatives: Mapped[int] = mapped_column(Integer, default=0)
    envoye_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
