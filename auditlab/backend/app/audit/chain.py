"""Chaînage par hash du journal d'audit (NF-02).

Chaque entrée contient le hash de la précédente ; son propre hash couvre tous ses champs.
Toute modification, insertion ou suppression d'une entrée passée rompt la chaîne.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

GENESIS_HASH = "0" * 64
# Identifiant arbitraire du verrou consultatif qui sérialise l'écriture du journal.
_CHAIN_LOCK_ID = 7_231_946_001


def to_json_safe(value: Any) -> Any:
    """Convertit une valeur en JSON pur, pour que le hash recalculé depuis JSONB soit identique."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(entry: AuditLog) -> str:
    payload = _canonical(
        {
            "seq": entry.seq,
            "horodatage": entry.horodatage.astimezone(UTC).isoformat(),
            "user_id": str(entry.user_id) if entry.user_id else None,
            "action": entry.action,
            "object_type": entry.object_type,
            "object_id": entry.object_id,
            "avant": entry.avant,
            "apres": entry.apres,
            "hash_precedent": entry.hash_precedent,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_entry(
    *,
    action: str,
    user_id: uuid.UUID | None,
    object_type: str | None = None,
    object_id: Any = None,
    avant: dict[str, Any] | None = None,
    apres: dict[str, Any] | None = None,
) -> AuditLog:
    """Prépare une entrée ; seq et hashes sont posés au moment du flush (voir seal_pending)."""
    return AuditLog(
        id=uuid.uuid4(),
        horodatage=datetime.now(UTC),
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        avant=to_json_safe(avant),
        apres=to_json_safe(apres),
    )


def seal_pending(session: Session, entries: list[AuditLog]) -> None:
    """Attribue seq, hash_precedent et hash aux nouvelles entrées, sous verrou transactionnel."""
    if not entries:
        return
    conn = session.connection()
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_ID})
    last = conn.execute(
        select(AuditLog.seq, AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1)
    ).first()
    seq, prev = (last.seq, last.hash) if last else (0, GENESIS_HASH)
    for entry in entries:
        seq += 1
        entry.seq = seq
        entry.hash_precedent = prev
        entry.hash = compute_hash(entry)
        prev = entry.hash


@dataclass
class ChainReport:
    ok: bool
    entries: int
    first_broken_seq: int | None = None
    reason: str | None = None


def verify_chain(session: Session, batch_size: int = 5000) -> ChainReport:
    """Recalcule toute la chaîne : continuité des numéros, des liens et des hashes."""
    prev_hash = GENESIS_HASH
    expected_seq = 1
    count = 0
    last_seq = 0
    while True:
        rows = session.scalars(
            select(AuditLog).where(AuditLog.seq > last_seq).order_by(AuditLog.seq).limit(batch_size)
        ).all()
        if not rows:
            break
        for entry in rows:
            if entry.seq != expected_seq:
                return ChainReport(False, count, expected_seq, "entrée manquante")
            if entry.hash_precedent != prev_hash:
                return ChainReport(False, count, entry.seq, "lien vers l'entrée précédente rompu")
            if compute_hash(entry) != entry.hash:
                return ChainReport(False, count, entry.seq, "contenu modifié")
            prev_hash = entry.hash
            expected_seq += 1
            count += 1
            last_seq = entry.seq
        session.expunge_all()
    return ChainReport(True, count)
