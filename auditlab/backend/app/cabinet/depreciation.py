"""Calcul des amortissements (RCO-11) : linéaire, dégressif, par composants.

- Linéaire : prorata temporis en jours sur une année de 360 jours (mois de 30 jours), du jour
  de mise en service au jour de cession inclus.
- Dégressif : taux = coefficient / durée, appliqué à la valeur nette du début de chaque
  exercice, à partir du premier jour du mois de mise en service (prorata en mois la première
  année) ; passage au linéaire dès que l'annuité linéaire sur la durée restante est
  supérieure. Le coefficient, valeur fiscale propre à chaque pays, est saisi.
- Un composant est une immobilisation à part entière, rattachée à son ensemble.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)


@dataclass
class Asset:
    valeur: Decimal
    mise_en_service: dt.date
    duree: int
    mode: str  # lineaire, degressif
    coefficient: Decimal | None = None
    cession: dt.date | None = None


def days360(start: dt.date, end: dt.date) -> int:
    """Jours entre deux dates incluses, base 30/360 (méthode européenne)."""
    d1, d2 = min(start.day, 30), min(end.day, 30)
    return (end.year - start.year) * 360 + (end.month - start.month) * 30 + (d2 - d1) + 1


def _months(start: dt.date, end: dt.date) -> int:
    """Mois entamés du mois de `start` au mois de `end` inclus."""
    return (end.year - start.year) * 12 + end.month - start.month + 1


def cumulated(a: Asset, at: dt.date, ends: Callable[[int], dt.date], q: Decimal) -> Decimal:
    """Amortissements cumulés au jour `at` inclus ; `ends(année)` donne la clôture d'un
    exercice (pour l'échéancier dégressif)."""
    stop = min(at, a.cession) if a.cession else at
    if stop < a.mise_en_service or a.valeur <= 0:
        return ZERO
    if a.mode == "lineaire":
        total = a.valeur * Decimal(days360(a.mise_en_service, stop)) / Decimal(360 * a.duree)
        return min(a.valeur, total).quantize(q, ROUND_HALF_UP)
    rate = (a.coefficient or Decimal(1)) / Decimal(a.duree)
    first = a.mise_en_service.replace(day=1)
    used_months, cumul = 0, ZERO
    year = (
        a.mise_en_service.year
        if ends(a.mise_en_service.year) >= a.mise_en_service
        else (a.mise_en_service.year + 1)
    )
    period_start = first
    while cumul < a.valeur:
        end = ends(year)
        last = min(end, stop)
        months = _months(period_start, last) if last >= period_start else 0
        net = a.valeur - cumul
        remaining = a.duree * 12 - used_months
        if remaining <= 0 or months <= 0:
            break
        degressive = net * rate * Decimal(months) / 12
        linear = net * Decimal(min(months, remaining)) / Decimal(remaining)
        annuity = min(net, max(degressive, linear)).quantize(q, ROUND_HALF_UP)
        cumul += annuity
        used_months += months
        if last < end:
            break
        period_start = end + dt.timedelta(days=1)
        year += 1
    return min(cumul, a.valeur)


def schedule(
    a: Asset, start: dt.date, end: dt.date, ends: Callable[[int], dt.date], q: Decimal
) -> dict[str, Decimal]:
    """Amortissements de l'exercice [start, end] : cumul début, dotation, cumul fin, VNC."""
    before = cumulated(a, start - dt.timedelta(days=1), ends, q)
    after = cumulated(a, end, ends, q)
    return {
        "cumul_debut": before,
        "dotation": after - before,
        "cumul_fin": after,
        "vnc": a.valeur - after,
    }
