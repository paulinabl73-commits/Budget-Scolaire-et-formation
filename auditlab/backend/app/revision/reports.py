"""Rapports paramétrables (REV-27) : opinion (sans réserve, avec réserve, défavorable,
impossibilité d'exprimer une opinion), rapport spécial sur les conventions réglementées,
lettre d'affirmation de la direction.

Un modèle est une suite de sections (titre, texte à variables, condition « si » : type
d'opinion ou « observations ») ; les montants viennent des états révisés selon les bases du
référentiel (total du bilan, capitaux propres, résultat).
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.models.revision import ReportTemplate

OPINIONS = ("sans_reserve", "avec_reserve", "defavorable", "impossibilite")
NO_CONVENTION = (
    "Nous vous informons qu'il ne nous a été donné avis d'aucune convention "
    "réglementée conclue au cours de l'exercice."
)


class _Values(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def seed(db: Any) -> None:
    """Installe les modèles livrés (tests ; en exploitation, migrations 0048 et 0072)."""
    root = Path(__file__).parents[1]
    for path in (
        root / "revision/data/rapports.json",
        root / "cabinet/data/documents_cloture.json",
    ):
        for m in json.loads(path.read_text("utf-8"))["modeles"]:
            db.add(ReportTemplate(code=m["code"], nom=m["nom"], sections=m["sections"]))


def amount(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.0f}".replace(",", " ")


def conventions_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return NO_CONVENTION
    lines = []
    for c in items:
        line = f"• {c.get('objet', '')} — parties : {c.get('parties', '')}"
        if c.get("modalites"):
            line += f" ; modalités : {c['modalites']}"
        if c.get("montant") not in (None, ""):
            line += f" ; montant : {c['montant']}"
        lines.append(line)
    return "\n".join(lines)


def blocks(template: ReportTemplate, opinion: Any, values: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in template.sections:
        condition = section.get("si")
        if condition == "observations" and not (opinion.observations or "").strip():
            continue
        if condition in OPINIONS and condition != opinion.type_opinion:
            continue
        if section.get("titre"):
            out.append({"titre": section["titre"]})
        out.append({"texte": section["texte"].format_map(_Values(values))})
    return out
