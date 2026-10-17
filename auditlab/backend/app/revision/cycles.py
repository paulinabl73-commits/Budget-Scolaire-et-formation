"""Cycles de révision, assertions et combinaison des risques (REV-14, réutilisés par REV-15).

La bibliothèque (data/cycles.json) est une donnée méthodologique : cycles et racines de
comptes par référentiel, assertions et procédures types, grille de combinaison du risque
inhérent et du risque lié au contrôle en risque d'anomalie significative (ISA 315).
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_FRAMEWORK = "SYSCOHADA"


@lru_cache
def library() -> dict[str, Any]:
    path = Path(__file__).parent / "data" / "cycles.json"
    return json.loads(path.read_text(encoding="utf-8"))


def cycles_for(framework_code: str) -> list[dict[str, Any]]:
    """Cycles du référentiel ; à défaut, ceux de SYSCOHADA (même structure de classes)."""
    by_framework = library()["cycles"]
    return by_framework.get(framework_code, by_framework[DEFAULT_FRAMEWORK])


def assertions() -> list[dict[str, Any]]:
    return library()["assertions"]


def cycle_of(compte: str, cycles: list[dict[str, Any]]) -> str | None:
    """Cycle dont la racine est la plus longue à couvrir le compte."""
    best: tuple[int, str] | None = None
    for cycle in cycles:
        for root in cycle["racines"]:
            if compte.startswith(root) and (best is None or len(root) > best[0]):
                best = (len(root), cycle["code"])
    return best[1] if best else None


def combined(inherent: str | None, control: str | None, significant: bool) -> str | None:
    """Risque d'anomalie significative ; un risque important (ISA 315) est toujours élevé."""
    if significant:
        return "eleve"
    if inherent is None or control is None:
        return None
    return library()["combinaison"][inherent][control]
