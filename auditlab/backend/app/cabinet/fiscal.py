"""Paramètres fiscaux par pays et par exercice (RCO-22) : un paramètre vaut à partir de son
exercice jusqu'à ce qu'un paramètre plus récent le remplace ; un paramètre sans exercice vaut
pour tous les exercices."""

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.portfolio import FiscalParameter


@lru_cache
def catalog() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "data" / "fiscal_parametres.json"
    return json.loads(path.read_text(encoding="utf-8"))["parametres"]


def resolve(db: Session, pays: str, exercice: int, code: str) -> FiscalParameter | None:
    rows = db.scalars(
        select(FiscalParameter).where(
            FiscalParameter.pays == pays,
            FiscalParameter.code == code,
            FiscalParameter.deleted_at.is_(None),
        )
    )
    eligible = [p for p in rows if p.exercice is None or p.exercice <= exercice]
    return max(eligible, key=lambda p: p.exercice or 0, default=None)


def values(db: Session, pays: str, exercice: int, codes: list[str]) -> dict[str, Decimal]:
    """Valeurs demandées ; 409 listant les paramètres manquants."""
    out, missing = {}, []
    for code in codes:
        p = resolve(db, pays, exercice, code)
        if p is None:
            missing.append(code)
        else:
            out[code] = p.valeur
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": f"Paramètres fiscaux à saisir pour {pays} et l'exercice {exercice} : "
                + ", ".join(missing),
                "points": missing,
            },
        )
    return out
