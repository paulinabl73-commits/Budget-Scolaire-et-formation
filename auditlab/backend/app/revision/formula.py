"""Formules des postes, ratios et règles d'un référentiel : codes de postes, nombres,
+ - * / et parenthèses. Analyse fermée : aucune évaluation de code Python."""

import re
from collections.abc import Mapping
from decimal import Decimal, DivisionByZero, InvalidOperation

TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([A-Za-z][A-Za-z0-9_]*)|(.))")


# Suffixe désignant le montant de l'exercice précédent d'un poste (ex. « BT_N1 »).
PREVIOUS = "_N1"


class FormulaError(ValueError):
    pass


def tokens(formula: str) -> list[tuple[str, str]]:
    out = []
    for number, name, op in TOKEN.findall(formula):
        if number:
            out.append(("n", number))
        elif name:
            out.append(("c", name))
        elif op.strip():
            if op not in "+-*/()":
                raise FormulaError(f"Caractère non admis « {op} » dans « {formula} »")
            out.append(("o", op))
    return out


def references(formula: str) -> set[str]:
    return {v for k, v in tokens(formula) if k == "c"}


def evaluate(formula: str, values: Mapping[str, Decimal]) -> Decimal | None:
    """Valeur de la formule ; None si une division par zéro survient."""
    toks = tokens(formula)
    pos = 0

    def peek() -> tuple[str, str] | None:
        return toks[pos] if pos < len(toks) else None

    def take() -> tuple[str, str]:
        nonlocal pos
        if pos >= len(toks):
            raise FormulaError(f"Formule incomplète « {formula} »")
        pos += 1
        return toks[pos - 1]

    def expr() -> Decimal:
        value = term()
        while (t := peek()) and t[1] in "+-" and t[0] == "o":
            take()
            value = value + term() if t[1] == "+" else value - term()
        return value

    def term() -> Decimal:
        value = factor()
        while (t := peek()) and t[1] in "*/" and t[0] == "o":
            take()
            right = factor()
            value = value * right if t[1] == "*" else value / right
        return value

    def factor() -> Decimal:
        kind, val = take()
        if kind == "o" and val == "-":
            return -factor()
        if kind == "o" and val == "(":
            value = expr()
            if take() != ("o", ")"):
                raise FormulaError(f"Parenthèse manquante dans « {formula} »")
            return value
        if kind == "n":
            return Decimal(val)
        if kind == "c":
            return values.get(val, Decimal(0))
        raise FormulaError(f"Formule invalide « {formula} »")

    try:
        result = expr()
    except (DivisionByZero, InvalidOperation):
        return None
    if pos != len(toks):
        raise FormulaError(f"Formule invalide « {formula} »")
    return result
