"""Pièces demandées au client (RCO-04) : statut et relances automatiques."""

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.portfolio import Client, PieceRequest
from app.notify import notify


@lru_cache
def standard_pieces() -> list[dict]:
    path = Path(__file__).parent / "data" / "pieces_types.json"
    return json.loads(path.read_text(encoding="utf-8"))["pieces"]


def status_of(p: PieceRequest, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    if p.recue_le:
        return "recue"
    if p.envoyee_le is None:
        return "a_envoyer"
    return "manquante" if p.date_limite < today else "demandee"


def remind(db: Session, client: Client, pieces: list[PieceRequest], today: dt.date) -> int:
    """Relance le contact du client pour les pièces données ; notées dans chaque pièce."""
    if not pieces or client.contact_id is None:
        return 0
    lines = "\n".join(f"- {p.libelle} (attendue le {p.date_limite:%d/%m/%Y})" for p in pieces)
    notify(
        db,
        {client.contact_id},
        "pieces_relance",
        f"{client.raison_sociale} : {len(pieces)} pièce(s) attendue(s)",
        f"Votre cabinet attend encore les pièces suivantes :\n{lines}\n"
        "Déposez-les depuis votre portail.",
        lien="/",
    )
    for p in pieces:
        p.relances = [*(p.relances or []), today.isoformat()]
    return len(pieces)


def send_piece_reminders(db: Session, today: dt.date | None = None) -> int:
    """Relance automatique des pièces envoyées non reçues, une fois la date limite passée,
    puis tous les `relance_pieces_jours` jours."""
    today = today or dt.date.today()
    every = dt.timedelta(days=get_settings().relance_pieces_jours)
    rows = db.scalars(
        select(PieceRequest).where(
            PieceRequest.deleted_at.is_(None),
            PieceRequest.recue_le.is_(None),
            PieceRequest.envoyee_le.is_not(None),
            PieceRequest.date_limite < today,
        )
    ).all()
    by_client: dict = {}
    for p in rows:
        last = max((dt.date.fromisoformat(d) for d in p.relances or []), default=None)
        if last is None or today - last >= every:
            by_client.setdefault(p.client_id, []).append(p)
    count = sum(remind(db, db.get(Client, cid), items, today) for cid, items in by_client.items())
    db.commit()
    return count
