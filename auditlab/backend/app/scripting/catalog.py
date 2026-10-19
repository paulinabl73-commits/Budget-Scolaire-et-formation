"""Bibliothèque de tests livrés (DAT-28) : métadonnées dans `library.json`, code dans
`library/<référence>.py`. Installés publiés par la migration 0075 (tests : `seed`)."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

from app.models.data import ScriptTemplate

ROOT = Path(__file__).resolve().parent


def catalog() -> dict[str, Any]:
    return json.loads((ROOT / "library.json").read_text("utf-8"))


def cycles() -> dict[str, str]:
    return catalog()["cycles"]


def seed(db: Any) -> None:
    now = dt.datetime.now(dt.UTC)
    for m in catalog()["modeles"]:
        db.add(ScriptTemplate(
            reference=m["code"], cycle=m["cycle"], nom=m["nom"], objectif=m["objectif"],
            colonnes=m["colonnes"], indicateur=m["indicateur"], statut="publie", version=1,
            code=(ROOT / "library" / f"{m['code']}.py").read_text("utf-8"), publie_le=now,
        ))  # fmt: skip
