"""Tableau de bord du portefeuille (RCO-02) et étapes de chaque clôture."""

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.permanent import expired
from app.api.portfolio import can_manage_client, closing_out, get_client, visible_clients
from app.cabinet.calendar import client_deadlines
from app.models.portfolio import Client, Closing
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Portefeuille (Module 6)"])
STAGES = ("pieces", "saisie", "revision", "revue", "depot", "termine")
# Au-delà de la revue, l'expert-comptable (ou le superviseur) décide.
MANAGER_STAGES = ("depot", "termine")
HORIZON_DAYS = 30


class StageIn(BaseModel):
    etape: Literal[STAGES]  # type: ignore[valid-type]
    date: dt.date | None = None


def latest_closing(db: Any, client: Client) -> Closing | None:
    return db.scalar(
        select(Closing)
        .where(Closing.client_id == client.id, Closing.deleted_at.is_(None))
        .order_by(Closing.exercice.desc())
        .limit(1)
    )


def progress(stage: str) -> int:
    return round(STAGES.index(stage) * 100 / (len(STAGES) - 1))


@router.put("/closings/{closing_id}/stage")
def set_stage(
    closing_id: uuid.UUID, body: StageIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    closing = db.get(Closing, closing_id)
    if closing is None or closing.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clôture introuvable")
    client = get_client(db, closing.client_id, user)
    manager = can_manage_client(client, user) or client.superviseur_id == user.id
    if not (manager or has_permission(user.role, Perm.REVISION_WORK)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'équipe du dossier")
    if body.etape in MANAGER_STAGES and not manager:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Dépôt et fin de clôture : expert-comptable ou superviseur"
        )
    current, wanted = STAGES.index(closing.etape), STAGES.index(body.etape)
    if wanted > current + 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Les étapes se franchissent une à une")
    day = body.date or dt.date.today()
    closing.etape = body.etape
    # Retour en arrière : les dates des étapes suivantes sont effacées.
    closing.etapes = {
        **{k: v for k, v in closing.etapes.items() if STAGES.index(k) < wanted},
        body.etape: day.isoformat(),
    }
    closing.date_depot = (
        dt.date.fromisoformat(closing.etapes["depot"]) if "depot" in closing.etapes else None
    )
    db.commit()
    return closing_out(closing)


@router.get("/portfolio/dashboard")
def dashboard(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    today = dt.date.today()
    rows, upcoming, counts = [], [], dict.fromkeys(STAGES, 0)
    clients = db.scalars(
        visible_clients(user).where(Client.actif.is_(True)).order_by(Client.raison_sociale)
    )
    for client in clients:
        closing = latest_closing(db, client)
        items = client_deadlines(
            db, client, today - dt.timedelta(days=365), today + dt.timedelta(days=HORIZON_DAYS)
        )
        late = [d for d in items if d["statut"] == "en_retard"]
        # Une échéance liée à la clôture, passée sans dépôt, met la clôture en retard.
        filing_late = (
            closing is not None
            and closing.date_depot is None
            and any(
                d["statut"] != "fait"
                and d["echeance"] < today.isoformat()
                and d["periode"] == f"exercice {closing.exercice}"
                for d in items
            )
        )
        if closing is not None:
            counts[closing.etape] += 1
        nxt = [d for d in items if d["statut"] == "a_venir"]
        upcoming += [
            {**d, "client_id": str(client.id), "client": client.raison_sociale} for d in nxt
        ]
        rows.append(
            {
                "client_id": str(client.id),
                "client": client.raison_sociale,
                "collaborateur_id": str(client.collaborateur_id)
                if client.collaborateur_id
                else None,
                "cloture": closing_out(closing) if closing else None,
                "avancement": progress(closing.etape) if closing else 0,
                "prochaine_echeance": nxt[0] if nxt else None,
                "echeances_en_retard": len(late),
                "en_retard": bool(late) or filing_late,
                "documents_expires": len(expired(db, client, today)),
            }
        )
    return {
        "dossiers": rows,
        "par_etape": counts,
        "echeances_a_venir": sorted(upcoming, key=lambda d: d["echeance"]),
        "dossiers_en_retard": [r["client"] for r in rows if r["en_retard"]],
        "horizon_jours": HORIZON_DAYS,
    }
