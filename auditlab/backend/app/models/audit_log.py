import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Journal d'audit en ajout seul, chaîné par hash (NF-01, NF-02).

    Volontairement sans clé étrangère : le journal doit survivre à tout objet métier.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    object_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    object_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    avant: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    apres: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    hash_precedent: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
