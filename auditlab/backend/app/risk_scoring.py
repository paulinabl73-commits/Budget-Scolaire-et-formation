"""Calcul du score de risque (AUD-02).

Échelle des notes : 1 (faible) à 5 (très élevé).
- score = Σ(poids × note) / Σ(poids × 5) × 100, sur 100 ;
- impact et probabilité = moyennes pondérées des critères de chaque axe, de 1 à 5 ;
- critère « ancienneté » : jamais audité → 5, sinon 1 + nombre d'années pleines depuis le
  dernier audit, plafonné à 5.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

NOTE_MIN = 1
NOTE_MAX = 5


@dataclass(frozen=True)
class CriterionSpec:
    code: str
    libelle: str
    axe: str
    mode: str
    poids: float


@dataclass
class ScoreResult:
    score: float
    impact: float | None
    probabilite: float | None
    criteres: list[dict[str, Any]]


def seniority_note(last_audit: date | None, on: date) -> int:
    if last_audit is None:
        return NOTE_MAX
    full_years = (
        on.year - last_audit.year - ((on.month, on.day) < (last_audit.month, last_audit.day))
    )
    return max(NOTE_MIN, min(NOTE_MAX, 1 + max(full_years, 0)))


def _weighted_mean(rows: list[dict[str, Any]]) -> float | None:
    total = sum(r["poids"] for r in rows)
    if not rows or total == 0:
        return None
    return round(sum(r["poids"] * r["note"] for r in rows) / total, 2)


def compute_score(
    criteria: list[CriterionSpec],
    notes: dict[str, int],
    last_audit: date | None,
    on: date,
) -> ScoreResult:
    """`notes` doit contenir une note entière 1–5 pour chaque critère en mode « note »."""
    rows: list[dict[str, Any]] = []
    for c in criteria:
        if c.mode == "anciennete":
            note = seniority_note(last_audit, on)
        else:
            if c.code not in notes:
                raise ValueError(f"Note manquante pour le critère « {c.libelle} »")
            note = notes[c.code]
            if not NOTE_MIN <= note <= NOTE_MAX:
                raise ValueError(
                    f"Note hors échelle pour « {c.libelle} » ({NOTE_MIN} à {NOTE_MAX})"
                )
        rows.append(
            {
                "code": c.code,
                "libelle": c.libelle,
                "axe": c.axe,
                "mode": c.mode,
                "poids": c.poids,
                "note": note,
            }
        )
    unknown = set(notes) - {c.code for c in criteria}
    if unknown:
        raise ValueError(f"Critère inconnu ou inactif : {', '.join(sorted(unknown))}")
    max_total = sum(r["poids"] for r in rows) * NOTE_MAX
    if max_total == 0:
        raise ValueError("Aucun critère actif : paramétrez au moins un critère")
    score = round(sum(r["poids"] * r["note"] for r in rows) / max_total * 100, 1)
    return ScoreResult(
        score=score,
        impact=_weighted_mean([r for r in rows if r["axe"] == "impact"]),
        probabilite=_weighted_mean([r for r in rows if r["axe"] == "probabilite"]),
        criteres=rows,
    )
