"""Revue du dossier de clôture (RCO-23) : visa du superviseur puis de l'expert-comptable,
sur les signatures des papiers de travail et les notes de revue du Module 1 (AUD-18 à
AUD-20). Le dépôt (RCO-02) exige le visa de l'expert-comptable.

Points bloquants : papiers non revus (superviseur) ou non approuvés (expert), notes de revue
ouvertes, comptes de bilan signalés (RCO-09), écritures d'inventaire en attente, anomalies
des check-lists (RCO-07) ; pour l'expert, états du référentiel non produits ou incohérents
(RCO-24)."""

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.closing_checklist import build as checklist
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import build as justifications
from app.api.pieces import _closing
from app.api.portfolio import can_manage_client, closing_out
from app.api.signoffs import signoffs_by_workpaper, status_of
from app.models.portfolio import Client, Closing
from app.models.revision import Adjustment, AuditFile
from app.models.user import User
from app.models.workpaper import ReviewNote, Workpaper

router = APIRouter(tags=["Portefeuille (Module 6)"])
LEVELS = ("superviseur", "expert")


class ReviewIn(BaseModel):
    niveau: Literal["superviseur", "expert"]
    commentaire: str | None = None


def blockers(db: Session, closing: Closing, client: Client, level: str) -> list[str]:
    file = db.get(AuditFile, closing.audit_file_id)
    papers = list(
        db.scalars(
            select(Workpaper).where(
                Workpaper.engagement_id == closing.engagement_id, Workpaper.deleted_at.is_(None)
            )
        )
    )
    states = signoffs_by_workpaper(db, [p.id for p in papers])
    wanted = ("revu", "approuve") if level == "superviseur" else ("approuve",)
    out = []
    late = sorted(p.reference for p in papers if status_of(states[p.id]) not in wanted)
    if late:
        label = "revus" if level == "superviseur" else "approuvés"
        out.append(f"Papiers de travail non {label} : " + ", ".join(late))
    notes = db.scalar(
        select(func.count())
        .select_from(ReviewNote)
        .where(
            ReviewNote.engagement_id == closing.engagement_id,
            ReviewNote.statut == "ouverte",
            ReviewNote.deleted_at.is_(None),
        )
    )
    if notes:
        out.append(f"{notes} note(s) de revue ouverte(s)")
    try:
        flagged = justifications(db, file)["signales"]
    except Exception:  # noqa: BLE001 - pas encore de balance : rien à justifier
        flagged = 0
    if flagged:
        out.append(f"{flagged} compte(s) de bilan signalé(s) à la justification")
    pending = db.scalar(
        select(func.count())
        .select_from(Adjustment)
        .where(
            Adjustment.audit_file_id == file.id,
            Adjustment.statut == "proposee",
            Adjustment.deleted_at.is_(None),
        )
    )
    if pending:
        out.append(f"{pending} écriture(s) en attente de décision")
    anomalies = [
        p["code"]
        for c in checklist(db, closing, client)["cycles"]
        for p in c["points"]
        if p["statut"] == "anomalie"
    ]
    if anomalies:
        out.append("Anomalies de check-list à lever : " + ", ".join(anomalies))
    if level == "expert":
        # RCO-24 : états du référentiel produits et cohérents (REV-23, REV-24).
        from app.revision import statements
        from app.revision.mapping import UnmappedError

        try:
            states = statements.build(db, file)
        except UnmappedError:
            out.append("États financiers non produits : balance N absente ou comptes non affectés")
        else:
            gaps = [c["libelle"] for c in states.get("controles", []) if not c["ok"]]
            if gaps:
                out.append("Contrôles des états en écart : " + ", ".join(gaps))
    if level == "expert" and client.superviseur_id and "superviseur" not in closing.revues:
        out.append("Visa du superviseur attendu")
    return out


def overview(db: Session, closing: Closing, client: Client, user: User) -> dict[str, Any]:
    return {
        **closing_out(closing),
        "revues": closing.revues,
        "blocages": {lvl: blockers(db, closing, client, lvl) for lvl in LEVELS},
        "superviseur_requis": client.superviseur_id is not None,
        "peut_viser": {
            "superviseur": user.id in (client.superviseur_id, client.expert_id)
            or can_manage_client(client, user),
            "expert": can_manage_client(client, user),
        },
    }


@router.get("/closings/{closing_id}/review")
def read_review(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    return overview(db, closing, client, user)


@router.post("/closings/{closing_id}/review")
def sign_review(
    closing_id: uuid.UUID, body: ReviewIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    allowed = overview(db, closing, client, user)["peut_viser"][body.niveau]
    if not allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Visa réservé au superviseur ou à l'expert-comptable"
        )
    if body.niveau in closing.revues:
        raise HTTPException(status.HTTP_409_CONFLICT, "Visa déjà donné")
    points = blockers(db, closing, client, body.niveau)
    if points:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": "; ".join(points), "points": points}
        )
    closing.revues = {
        **closing.revues,
        body.niveau: {
            "le": dt.datetime.now(dt.UTC).isoformat(),
            "par": user.nom,
            "commentaire": body.commentaire,
        },
    }
    db.commit()
    return overview(db, closing, client, user)


@router.delete("/closings/{closing_id}/review/{niveau}")
def withdraw_review(
    closing_id: uuid.UUID, niveau: str, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Retire un visa (et celui de l'expert avec celui du superviseur) avant le dépôt."""
    closing, client = _closing(db, closing_id, user)
    if not can_manage_client(client, user) and user.id != client.superviseur_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé au superviseur ou à l'expert-comptable"
        )
    if closing.date_depot is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Comptes déjà déposés")
    if (closing.documents or {}).get("signature"):
        raise HTTPException(  # RCO-25 : l'attestation repose sur le visa de l'expert.
            status.HTTP_409_CONFLICT, "Attestation de présentation signée : annulez-la d'abord"
        )
    drop = {"superviseur", "expert"} if niveau == "superviseur" else {niveau}
    closing.revues = {k: v for k, v in closing.revues.items() if k not in drop}
    db.commit()
    return overview(db, closing, client, user)
