"""Modèle de rapport livré (REP-01) : installé par la migration 0077 (tests : `seed`)."""

import json
from pathlib import Path
from typing import Any

from app.models.report import MissionReportTemplate

DATA = Path(__file__).resolve().parent / "data" / "modele_rapport.json"


def default_spec() -> dict[str, Any]:
    return json.loads(DATA.read_text("utf-8"))


def seed(db: Any) -> MissionReportTemplate:
    doc = default_spec()
    t = MissionReportTemplate(
        nom=doc["nom"], par_defaut=True, page_garde=doc["page_garde"], sections=doc["sections"],
        ordre_constats=doc["ordre_constats"], pied_de_page=doc["pied_de_page"], actif=True,
    )  # fmt: skip
    db.add(t)
    return t
