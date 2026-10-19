"""Check-lists de révision par cycle d'une clôture (RCO-07)."""

import datetime as dt
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.pieces import _closing, _require_team
from app.models.portfolio import ChecklistAnswer, Client, Closing
from app.models.revision import AccountingFramework

router = APIRouter(tags=["Portefeuille (Module 6)"])


@lru_cache
def library() -> list[dict[str, Any]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "checklists.json"
    return json.loads(path.read_text(encoding="utf-8"))["points"]


@lru_cache
def cycle_labels() -> dict[str, str]:
    path = Path(__file__).parents[1] / "revision" / "data" / "cycles.json"
    cycles = json.loads(path.read_text(encoding="utf-8"))["cycles"]["SYSCOHADA"]
    return {c["code"]: c["libelle"] for c in cycles}


class AnswerIn(BaseModel):
    statut: Literal["fait", "sans_objet", "anomalie"] | None
    commentaire: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _comment(self) -> "AnswerIn":
        if self.statut == "anomalie" and not (self.commentaire or "").strip():
            raise ValueError("Commentaire obligatoire pour une anomalie")
        return self


def points(db: Session, client: Client) -> list[dict[str, Any]]:
    """Points applicables selon la taille du dossier et le référentiel du client."""
    code = db.get(AccountingFramework, client.framework_id).code
    return [
        p
        for p in library()
        if client.taille in p["tailles"] and code in p.get("referentiels", [code])
    ]


def build(db: Session, closing: Closing, client: Client) -> dict[str, Any]:
    answers = {
        a.code: a
        for a in db.scalars(
            select(ChecklistAnswer).where(
                ChecklistAnswer.closing_id == closing.id, ChecklistAnswer.deleted_at.is_(None)
            )
        )
    }
    labels = cycle_labels()
    cycles: dict[str, dict[str, Any]] = {}
    for p in points(db, client):
        a = answers.get(p["code"])
        group = cycles.setdefault(
            p["cycle"],
            {"cycle": p["cycle"], "libelle": labels.get(p["cycle"], p["cycle"]), "points": []},
        )
        group["points"].append(
            {
                "code": p["code"],
                "libelle": p["libelle"],
                "statut": a.statut if a else None,
                "commentaire": a.commentaire if a else None,
            }
        )
    items = [pt for c in cycles.values() for pt in c["points"]]
    done = sum(pt["statut"] is not None for pt in items)
    return {
        "cycles": list(cycles.values()),
        "total": len(items),
        "traites": done,
        "anomalies": sum(pt["statut"] == "anomalie" for pt in items),
        "avancement": round(done * 100 / len(items)) if items else 100,
    }


@router.get("/closings/{closing_id}/checklist")
def read_checklist(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    return build(db, closing, client)


@router.put("/closings/{closing_id}/checklist/{code}")
def answer(
    closing_id: uuid.UUID, code: str, body: AnswerIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    _require_team(client, user)
    if code not in {p["code"] for p in points(db, client)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Point de contrôle non applicable")
    row = db.scalar(
        select(ChecklistAnswer).where(
            ChecklistAnswer.closing_id == closing.id,
            ChecklistAnswer.code == code,
            ChecklistAnswer.deleted_at.is_(None),
        )
    )
    if body.statut is None:
        if row is not None:  # réponse retirée (suppression logique, NF-03)
            row.deleted_at, row.deleted_by = dt.datetime.now(dt.UTC), user.id
    else:
        if row is None:
            row = ChecklistAnswer(closing_id=closing.id, code=code, statut=body.statut)
            db.add(row)
        row.statut, row.commentaire = body.statut, body.commentaire
    db.commit()
    return build(db, closing, client)
