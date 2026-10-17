"""Fonctions statistiques sans dépendance externe (lois du khi-deux et normale)."""

import math


def _gamma_series(a: float, x: float) -> float:
    total = term = 1.0 / a
    n = a
    for _ in range(1000):
        n += 1
        term *= x / n
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_fraction(a: float, x: float) -> float:
    # Fraction continue de Lentz (Numerical Recipes, gcf).
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gamma_q(a: float, x: float) -> float:
    """Fonction gamma incomplète régularisée supérieure Q(a, x)."""
    if x <= 0:
        return 1.0
    if x < a + 1:
        return 1.0 - _gamma_series(a, x)
    return _gamma_fraction(a, x)


def chi2_sf(statistic: float, dof: int) -> float:
    """p-valeur du test du khi-deux : P(X > statistic) pour dof degrés de liberté."""
    return gamma_q(dof / 2, statistic / 2)


def normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))
