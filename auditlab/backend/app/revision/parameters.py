"""Paramètres réglementaires par pays et par exercice (CIP-09).

Aucune valeur réglementaire n'est écrite dans le programme : chaque contrôle lit ses taux,
plafonds et limites ici. Un paramètre vaut à partir de son exercice jusqu'à ce qu'un
paramètre plus récent le remplace ; le plus précis l'emporte (branche, pays, puis exercice
le plus proche) ; un paramètre sans pays ou sans branche vaut pour tous.
"""

import json
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.revision import RegulatoryParameter


class MissingParameters(LookupError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__("Paramètres réglementaires manquants : " + ", ".join(missing))
        self.missing = missing


@lru_cache
def catalog() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "data" / "cipres_parametres.json"
    return json.loads(path.read_text(encoding="utf-8"))["parametres"]


def resolve(
    db: Session,
    framework_id: uuid.UUID,
    code: str,
    pays: str | None,
    exercice: int,
    branche: str | None = None,
) -> RegulatoryParameter | None:
    rows = db.scalars(
        select(RegulatoryParameter).where(
            RegulatoryParameter.framework_id == framework_id,
            RegulatoryParameter.code == code,
            RegulatoryParameter.deleted_at.is_(None),
        )
    )
    best, best_key = None, None
    for p in rows:
        if p.branche not in (None, branche) or p.pays not in (None, pays):
            continue
        if p.exercice is not None and p.exercice > exercice:
            continue
        key = (p.branche is not None, p.pays is not None, p.exercice or 0)
        if best_key is None or key > best_key:
            best, best_key = p, key
    return best


def values(
    db: Session,
    framework_id: uuid.UUID,
    pays: str | None,
    exercice: int,
    wanted: list[tuple[str, str | None]],
) -> dict[tuple[str, str | None], Decimal]:
    """Valeurs demandées (code, branche) ; MissingParameters si l'une manque."""
    out, missing = {}, []
    for code, branche in wanted:
        p = resolve(db, framework_id, code, pays, exercice, branche)
        if p is None:
            missing.append(f"{code}{f' ({branche})' if branche else ''}")
        else:
            out[(code, branche)] = p.valeur
    if missing:
        raise MissingParameters(missing)
    return out
