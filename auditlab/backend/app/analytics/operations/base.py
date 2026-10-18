"""Cadre commun des analyses (lot 6).

Une analyse est une opération déclarée une fois (code, tables d'entrée, paramètres typés,
fonction d'exécution). Elle lit ses entrées par `relation`, produit une table neuve (Parquet en
lecture seule) et un résultat de synthèse (tests, graphiques). Son exécution est déterministe :
mêmes entrées et mêmes paramètres donnent la même table, octet pour octet (NF-04) ; chaque
opération trie donc explicitement sa sortie.
"""

import datetime as dt
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import polars as pl

from app.analytics.relation import Relation

NUMERIC = ("entier", "decimal")
DATES = ("date", "date_heure")
TEXT = ("texte",)


class AnalysisError(ValueError):
    """Paramètres invalides ou analyse impossible ; message présenté à l'utilisateur."""


@dataclass(frozen=True)
class Param:
    nom: str
    # colonne, colonnes, nombre, entier, graine, nombres, texte, expression, choix, date,
    # agregats (liste {champ, fonction}), paires (liste {gauche, droite}),
    # bareme (valeur par code, ex. taux par branche : {"PF": 7} ou « PF=7; RP=2 »)
    type: str
    requis: bool = True
    defaut: Any = None
    choix: tuple[str, ...] = ()
    table: int = 0  # 0 = table principale, 1 = seconde table
    types_colonne: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None


@dataclass
class OpResult:
    df: pl.DataFrame
    resultat: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Operation:
    code: str
    exigence: str
    entrees: int
    params: tuple[Param, ...]
    run: Callable[[list[Relation], dict[str, Any]], OpResult]

    def describe(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "exigence": self.exigence,
            "entrees": self.entrees,
            "params": [asdict(p) for p in self.params],
        }


REGISTRY: dict[str, Operation] = {}


def register(op: Operation) -> Operation:
    REGISTRY[op.code] = op
    return op


def _number(value: Any, nom: str) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError) as exc:
        raise AnalysisError(f"{nom} : nombre attendu") from exc
    if not number.is_finite():
        raise AnalysisError(f"{nom} : nombre attendu")
    return number


def _column(value: Any, p: Param, schemas: list[dict[str, str]], nom: str) -> str:
    types = schemas[p.table]
    if not isinstance(value, str) or value not in types:
        raise AnalysisError(f"{nom} : colonne inconnue « {value} »")
    if p.types_colonne and types[value] not in p.types_colonne:
        raise AnalysisError(f"{nom} : la colonne « {value} » n'a pas le type attendu")
    return value


def _bounded(p: Param, number: Decimal) -> Decimal:
    if p.minimum is not None and number < Decimal(str(p.minimum)):
        raise AnalysisError(f"{p.nom} : valeur minimale {p.minimum}")
    if p.maximum is not None and number > Decimal(str(p.maximum)):
        raise AnalysisError(f"{p.nom} : valeur maximale {p.maximum}")
    return number


def validate(op: Operation, raw: dict[str, Any], rels: list[Relation]) -> dict[str, Any]:
    """Contrôle et normalise les paramètres (colonnes existantes, types, bornes)."""
    schemas = [r.types for r in rels]
    clean: dict[str, Any] = {}
    unknown = set(raw) - {p.nom for p in op.params}
    if unknown:
        raise AnalysisError(f"Paramètre inconnu « {sorted(unknown)[0]} »")
    for p in op.params:
        value = raw.get(p.nom)
        if p.type == "graine" and (value is None or value == ""):
            # DAT-22 : graine tirée au lancement puis conservée avec les paramètres.
            clean[p.nom] = secrets.randbelow(2**31 - 1)
            continue
        if value is None or value == "" or value == []:
            if p.requis and p.defaut is None:
                raise AnalysisError(f"{p.nom} : paramètre obligatoire")
            clean[p.nom] = p.defaut
            continue
        if p.type == "colonne":
            clean[p.nom] = _column(value, p, schemas, p.nom)
        elif p.type == "colonnes":
            if not isinstance(value, list) or len(value) > 10:
                raise AnalysisError(f"{p.nom} : liste de 1 à 10 colonnes attendue")
            cols = [_column(v, p, schemas, p.nom) for v in value]
            if len(set(cols)) != len(cols):
                raise AnalysisError(f"{p.nom} : colonne répétée")
            clean[p.nom] = cols
        elif p.type == "nombre":
            clean[p.nom] = str(_bounded(p, _number(value, p.nom)))
        elif p.type in ("entier", "graine"):
            number = _bounded(p, _number(value, p.nom))
            if number != number.to_integral_value():
                raise AnalysisError(f"{p.nom} : nombre entier attendu")
            clean[p.nom] = int(number)
        elif p.type == "nombres":
            if not isinstance(value, list) or not 1 <= len(value) <= 50:
                raise AnalysisError(f"{p.nom} : liste de 1 à 50 nombres attendue")
            numbers = [_number(v, p.nom) for v in value]
            if numbers != sorted(set(numbers)):
                raise AnalysisError(f"{p.nom} : valeurs croissantes et distinctes attendues")
            clean[p.nom] = [str(n) for n in numbers]
        elif p.type in ("texte", "expression"):
            if not isinstance(value, str) or len(value) > 4000:
                raise AnalysisError(f"{p.nom} : texte attendu")
            clean[p.nom] = value
        elif p.type == "choix":
            if value not in p.choix:
                raise AnalysisError(f"{p.nom} : valeur parmi {', '.join(p.choix)}")
            clean[p.nom] = value
        elif p.type == "date":
            try:
                clean[p.nom] = dt.date.fromisoformat(str(value)).isoformat()
            except ValueError as exc:
                raise AnalysisError(f"{p.nom} : date attendue (aaaa-mm-jj)") from exc
        elif p.type == "agregats":
            clean[p.nom] = _aggregates(value, schemas, p)
        elif p.type == "paires":
            clean[p.nom] = _pairs(value, schemas, p)
        elif p.type == "bareme":
            clean[p.nom] = _scale(value, p)
        else:  # pragma: no cover - déclaration erronée
            raise AssertionError(p.type)
    return clean


AGGREGATES = ("somme", "moyenne", "min", "max", "nombre", "distincts", "ecart_type")


def _aggregates(value: Any, schemas: list[dict[str, str]], p: Param) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 20:
        raise AnalysisError(f"{p.nom} : liste d'agrégats attendue (20 au plus)")
    out = []
    for item in value:
        if not isinstance(item, dict) or item.get("fonction") not in AGGREGATES:
            raise AnalysisError(f"{p.nom} : fonction parmi {', '.join(AGGREGATES)}")
        champ = _column(item.get("champ"), Param(p.nom, "colonne"), schemas, p.nom)
        if (
            item["fonction"] in ("somme", "moyenne", "ecart_type")
            and schemas[0][champ] not in NUMERIC
        ):
            raise AnalysisError(f"{p.nom} : « {champ} » n'est pas numérique")
        out.append({"champ": champ, "fonction": item["fonction"]})
    return out


def _pairs(value: Any, schemas: list[dict[str, str]], p: Param) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 5:
        raise AnalysisError(f"{p.nom} : 1 à 5 paires de clés attendues")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise AnalysisError(f"{p.nom} : paire {{gauche, droite}} attendue")
        left = _column(item.get("gauche"), Param(p.nom, "colonne", table=0), schemas, p.nom)
        right = _column(item.get("droite"), Param(p.nom, "colonne", table=1), schemas, p.nom)
        out.append({"gauche": left, "droite": right})
    return out


def _scale(value: Any, p: Param) -> dict[str, str]:
    if isinstance(value, str):
        items = [part.partition("=") for part in value.split(";") if part.strip()]
        if any(not sep for _, sep, _ in items):
            raise AnalysisError(f"{p.nom} : forme « CODE=valeur; CODE=valeur » attendue")
        value = {k.strip(): v.strip() for k, _, v in items}
    if not isinstance(value, dict) or not 1 <= len(value) <= 20:
        raise AnalysisError(f"{p.nom} : 1 à 20 valeurs attendues")
    out = {}
    for code, number in value.items():
        if not isinstance(code, str) or not code.isalnum() or len(code) > 20:
            raise AnalysisError(f"{p.nom} : code « {code} » invalide")
        out[code] = str(_bounded(p, _number(number, p.nom)))
    return out


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return None if value != value else round(value, 10)
    return value


def unique_name(name: str, taken: set[str]) -> str:
    """Nom de colonne libre : « montant », puis « montant_2 », « montant_3 »…"""
    candidate, i = name, 2
    while candidate.lower() in {t.lower() for t in taken}:
        candidate, i = f"{name}_{i}", i + 1
    taken.add(candidate)
    return candidate
