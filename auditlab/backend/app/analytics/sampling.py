"""Échantillonnage statistique (DAT-20 à DAT-23) : fonctions pures, testées seules.

Références : AICPA, Audit Guide « Audit Sampling » (2019) pour les tailles d'échantillon et
l'évaluation MUS ; ISA 530. Les facteurs de confiance sont calculés à partir de la loi de
Poisson (et non lus dans une table), ce qui reproduit les tables publiées.
"""

import math
import random
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.analytics.statistics import gamma_q

# Facteurs d'expansion de l'erreur attendue (AICPA, Audit Sampling, table 6.2), par niveau de
# confiance. Une valeur de confiance absente de la table prend le facteur immédiatement supérieur.
EXPANSION_FACTORS = {
    Decimal("0.99"): Decimal("1.9"),
    Decimal("0.975"): Decimal("1.7"),
    Decimal("0.95"): Decimal("1.6"),
    Decimal("0.90"): Decimal("1.5"),
    Decimal("0.85"): Decimal("1.4"),
    Decimal("0.80"): Decimal("1.3"),
    Decimal("0.75"): Decimal("1.25"),
    Decimal("0.70"): Decimal("1.2"),
    Decimal("0.63"): Decimal("1.15"),
}


class SamplingError(ValueError):
    pass


# --- Lois -------------------------------------------------------------------------------------


def poisson_cdf(k: int, lam: float) -> float:
    """P(X ≤ k) pour X de Poisson de paramètre lam."""
    return gamma_q(k + 1, lam) if lam > 0 else 1.0


def binomial_cdf(k: int, n: int, p: float) -> float:
    total = 0.0
    for i in range(k + 1):
        total += math.comb(n, i) * p**i * (1 - p) ** (n - i)
    return total


def poisson_factor(errors: int, confidence: float) -> float:
    """Facteur de limite supérieure : λ tel que P(X ≤ errors ; λ) = 1 − confiance."""
    risk = 1 - confidence
    low, high = 0.0, 10.0 + 3 * errors
    for _ in range(200):
        mid = (low + high) / 2
        if poisson_cdf(errors, mid) > risk:
            low = mid
        else:
            high = mid
    return high


def expansion_factor(confidence: Decimal) -> Decimal:
    eligible = [c for c in EXPANSION_FACTORS if c >= confidence]
    return (
        EXPANSION_FACTORS[min(eligible)] if eligible else EXPANSION_FACTORS[max(EXPANSION_FACTORS)]
    )


# --- Taille d'échantillon (DAT-21) ----------------------------------------------------------


def attribute_sample_size(confidence: float, tolerable_rate: float, expected_rate: float) -> int:
    """Tests de contrôles (sondage par attributs, loi binomiale, méthode AICPA).

    Plus petite taille n telle que, avec ⌈n × taux attendu⌉ écarts, le risque que le taux réel
    dépasse le taux tolérable soit au plus 1 − confiance.
    """
    if not 0 < tolerable_rate < 1 or not 0 <= expected_rate < tolerable_rate:
        raise SamplingError("Taux attendu inférieur au taux tolérable, tous deux entre 0 et 1")
    risk = 1 - confidence
    for n in range(1, 5001):
        k = math.ceil(n * expected_rate - 1e-9)
        if binomial_cdf(k, n, tolerable_rate) <= risk:
            return n
    raise SamplingError("Taille supérieure à 5 000 : revoir les paramètres")


def mus_sample_size(
    population: Decimal, confidence: Decimal, tolerable: Decimal, expected: Decimal
) -> int:
    """Sondage en unités monétaires : n = V × FC / (ET − EA × FE) (AICPA, table 6.1)."""
    margin = tolerable - expected * expansion_factor(confidence)
    if population <= 0 or tolerable <= 0 or margin <= 0:
        raise SamplingError("Erreur tolérable trop faible au regard de l'erreur attendue")
    factor = Decimal(str(round(poisson_factor(0, float(confidence)), 4)))
    return max(1, math.ceil(population * factor / margin))


# --- Sélection (DAT-20, DAT-22) -------------------------------------------------------------


def simple_random(population: int, size: int, seed: int) -> list[int]:
    if size > population:
        raise SamplingError("Échantillon plus grand que la population")
    return sorted(random.Random(seed).sample(range(population), size))  # noqa: S311


def systematic(population: int, size: int, seed: int) -> tuple[list[int], float, float]:
    if size > population:
        raise SamplingError("Échantillon plus grand que la population")
    step = population / size
    start = random.Random(seed).random() * step  # noqa: S311
    return [int(start + i * step) for i in range(size)], step, start


def stratified(strata: list[list[int]], size: int, seed: int) -> list[tuple[int, int]]:
    """Allocation proportionnelle (au moins une ligne par strate non vide) ; renvoie
    (rang de strate, ligne) triés par ligne."""
    total = sum(len(s) for s in strata)
    if size > total:
        raise SamplingError("Échantillon plus grand que la population")
    # Plus forts restes (méthode de Hamilton), puis au moins une ligne par strate non vide.
    quotas = [size * len(s) / total for s in strata]
    alloc = [int(q) for q in quotas]
    by_remainder = sorted(range(len(strata)), key=lambda i: (-(quotas[i] - alloc[i]), i))
    for i in by_remainder[: size - sum(alloc)]:
        alloc[i] += 1
    for i, s in enumerate(strata):
        if s and alloc[i] == 0:
            alloc[i] = 1
            j = max(range(len(strata)), key=lambda k: (alloc[k], -k))
            alloc[j] -= 1
    rng = random.Random(seed)  # noqa: S311
    picked = [(k, row) for k, s in enumerate(strata) for row in rng.sample(s, alloc[k])]
    return sorted(picked, key=lambda x: x[1])


@dataclass
class MusSelection:
    interval: Decimal
    start: Decimal
    hits: dict[int, list[Decimal]] = field(default_factory=dict)  # ligne → points de sélection


def monetary_unit(amounts: list[Decimal], size: int, seed: int) -> MusSelection:
    """Sélection systématique en unités monétaires sur les montants positifs ; une ligne
    supérieure à l'intervalle peut être tirée plusieurs fois (elle figure une fois)."""
    total = sum((a for a in amounts if a > 0), Decimal(0))
    if total <= 0:
        raise SamplingError("Aucun montant positif à échantillonner")
    interval = (total / size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if interval <= 0:
        raise SamplingError("Intervalle nul : réduire la taille de l'échantillon")
    unit = Decimal(str(random.Random(seed).random()))  # noqa: S311
    start = (unit * interval).quantize(Decimal("0.01"))
    selection = MusSelection(interval, start)
    point, cumulative = start, Decimal(0)
    for row, amount in enumerate(amounts):
        if amount <= 0:
            continue
        cumulative += amount
        while point < cumulative and point < total:
            selection.hits.setdefault(row, []).append(point)
            point += interval
    return selection


# --- Évaluation MUS (DAT-23) ------------------------------------------------------------------


@dataclass
class Misstatement:
    ligne: int
    comptable: Decimal
    audite: Decimal


def evaluate_mus(
    errors: list[Misstatement], interval: Decimal, confidence: float, tolerable: Decimal | None
) -> dict:
    """Projection des erreurs et limite supérieure (méthode de la « cellule » AICPA).

    - ligne ≥ intervalle : erreur réelle, sans projection ni provision ;
    - autre ligne : taux d'erreur (tainting) × intervalle, classés par taux décroissant, avec
      la provision d'élargissement (facteur incrémental − 1) ;
    - précision de base = facteur à 0 erreur × intervalle.
    Les surévaluations et les sous-évaluations sont évaluées séparément.
    """

    def side(items: list[Misstatement], sign: int) -> dict:
        top = Decimal(0)
        taints: list[Decimal] = []
        for e in items:
            diff = (e.comptable - e.audite) * sign
            if e.comptable >= interval:
                top += diff
            elif e.comptable != 0:
                taints.append(min(diff / e.comptable, Decimal(1)))
        taints.sort(reverse=True)
        basic = Decimal(str(poisson_factor(0, confidence))) * interval
        projected = sum((t * interval for t in taints), Decimal(0))
        allowance = Decimal(0)
        previous = poisson_factor(0, confidence)
        for i, t in enumerate(taints, start=1):
            factor = poisson_factor(i, confidence)
            allowance += t * interval * (Decimal(str(factor - previous)) - 1)
            previous = factor
        upper = top + basic + projected + allowance
        q = Decimal("0.01")
        return {
            "erreurs": len(items),
            "erreur_lignes_superieures": str(top.quantize(q)),
            "erreur_projetee": str((top + projected).quantize(q)),
            "precision_de_base": str(basic.quantize(q)),
            "provision_supplementaire": str(allowance.quantize(q)),
            "limite_superieure": str(upper.quantize(q)),
        }

    over = [e for e in errors if e.comptable > e.audite]
    under = [e for e in errors if e.comptable < e.audite]
    result = {
        "intervalle": str(interval),
        "confiance": confidence,
        "surevaluations": side(over, 1),
        "sous_evaluations": side(under, -1),
    }
    if tolerable is not None:
        upper = Decimal(result["surevaluations"]["limite_superieure"])
        result["erreur_tolerable"] = str(tolerable)
        result["conclusion"] = "acceptable" if upper <= tolerable else "non_acceptable"
    return result
