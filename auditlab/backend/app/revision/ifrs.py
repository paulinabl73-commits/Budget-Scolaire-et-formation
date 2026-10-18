"""Passage aux IFRS (IFR-01, IFR-03).

Les états IFRS sont calculés par la table de passage du référentiel de restitution : chaque
poste IFRS est une formule sur les postes SYSCOHADA révisés et retraités des écritures IFRS
validées (IFR-01), ou sur d'autres postes IFRS ; « CODE_N1 » renvoie au montant de l'exercice
précédent. Les comparatifs N-1 ne sont pas retraités (seuls les retraitements datés de
l'exercice N sont saisis) ; les retraitements de première application passent par les
capitaux propres d'ouverture (report à nouveau).

Réconciliations : capitaux propres et résultat SYSCOHADA → IFRS, par norme.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.models.revision import StatementLine
from app.revision.formula import PREVIOUS, evaluate, references

ZERO = Decimal(0)
EQUITY_ROOTS = ("10", "11", "12", "13", "14", "15")


def evaluate_lines(
    lines: list[StatementLine], base: dict[str, Decimal], previous: dict[str, Decimal] | None
) -> dict[str, Decimal]:
    """Montants des postes IFRS ; `base` = postes SYSCOHADA, `previous` = montants N-1 (postes
    IFRS et SYSCOHADA confondus)."""
    by_code = {ln.code: ln for ln in lines}
    values: dict[str, Decimal] = {}

    def value(code: str, stack: tuple[str, ...] = ()) -> Decimal:
        if code.endswith(PREVIOUS):
            return (previous or {}).get(code.removesuffix(PREVIOUS), ZERO)
        if code not in by_code:
            return base.get(code, ZERO)
        if code in values:
            return values[code]
        line = by_code[code]
        result = ZERO
        if line.formule and code not in stack:
            deps = {r: value(r, (*stack, code)) for r in references(line.formule)}
            result = evaluate(line.formule, deps) or ZERO
        values[code] = result
        return result

    for code in by_code:
        value(code)
    return values


def effects_by_standard(
    adjustments: list[Any], lines: dict[Any, list[Any]]
) -> dict[str, dict[str, Decimal]]:
    """Effet de chaque norme sur le résultat (classes de gestion) et sur les capitaux propres
    (résultat compris)."""
    classes = get_settings().classes_resultat
    out: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"resultat": ZERO, "capitaux": ZERO})
    for adj in adjustments:
        for ln in lines[adj.id]:
            effect = ln.credit - ln.debit
            if ln.compte[0] in classes:
                out[adj.norme]["resultat"] += effect
                out[adj.norme]["capitaux"] += effect
            elif ln.compte.startswith(EQUITY_ROOTS):
                out[adj.norme]["capitaux"] += effect
    return dict(out)
