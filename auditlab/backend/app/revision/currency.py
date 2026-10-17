"""Devises et conversion des montants importés (REV-07).

Les montants sont tenus dans la devise du dossier, arrondis à son nombre de décimales (zéro
pour le franc CFA). Un fichier tenu dans une autre devise est converti au cours enregistré à la
date choisie (par défaut la clôture de l'exercice) ; à défaut, au dernier cours connu avant
cette date, ce qu'un avertissement signale. Le cours inverse est utilisé s'il est le seul connu.
"""

import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.revision import Currency, ExchangeRate
from app.revision.balances import ImportError_
from app.revision.imports import PREPARE, Parsed


def seed_currencies(db: Session) -> None:
    """Devises de départ (également installées par la migration 0035)."""
    path = Path(__file__).parent / "data" / "devises.json"
    for item in json.loads(path.read_text(encoding="utf-8")):
        if db.scalar(select(Currency).where(Currency.code == item["code"])) is None:
            db.add(Currency(**item))


def decimals(db: Session, code: str) -> int:
    currency = db.scalar(
        select(Currency).where(Currency.code == code, Currency.deleted_at.is_(None))
    )
    return currency.decimales if currency is not None else 2


def quantum(places: int) -> Decimal:
    return Decimal(1).scaleb(-places)


def find_rate(db: Session, source: str, target: str, on: dt.date) -> tuple[Decimal, dt.date] | None:
    """Cours source → cible au plus tard à la date donnée (direct, sinon inverse)."""
    best: tuple[Decimal, dt.date] | None = None
    for a, b, invert in ((source, target, False), (target, source, True)):
        row = db.scalar(
            select(ExchangeRate)
            .where(
                ExchangeRate.devise_source == a,
                ExchangeRate.devise_cible == b,
                ExchangeRate.date <= on,
                ExchangeRate.deleted_at.is_(None),
            )
            .order_by(ExchangeRate.date.desc())
            .limit(1)
        )
        if row is not None and (best is None or row.date > best[1]):
            best = (Decimal(1) / row.taux if invert else row.taux, row.date)
    return best


def convert(db: Session, parsed: Parsed) -> None:
    req, file = parsed.request, parsed.file
    places = decimals(db, file.devise)
    q = quantum(places)
    rate = Decimal(1)
    if req.devise_source and req.devise_source != file.devise:
        on = req.date_cours or file.date_fin
        found = find_rate(db, req.devise_source, file.devise, on)
        if found is None:
            raise ImportError_(
                f"Aucun cours {req.devise_source} → {file.devise} enregistré au {on:%d/%m/%Y} "
                "ou avant : saisissez-le dans Référentiels › Devises et cours"
            )
        rate, used = found
        parsed.cours = rate.quantize(Decimal("1e-10"))
        if used != on:
            message = f"Pas de cours au {on:%d/%m/%Y} : cours du {used:%d/%m/%Y} appliqué"
            parsed.avertissements.append({"code": "cours_anterieur", "message": message})
    elif req.devise_source == file.devise:
        req.devise_source = None
    lost = Decimal(0)
    if parsed.ledger is not None:
        df = parsed.ledger
        for col in ("debit", "credit"):
            raw = [Decimal(v) * rate for v in df[col].to_list()]
            rounded = [v.quantize(q, ROUND_HALF_UP) for v in raw]
            lost += sum((abs(r - v) for r, v in zip(rounded, raw, strict=True)), Decimal(0))
            df = df.with_columns(pl.Series(col, rounded, dtype=pl.Decimal(20, 2)))
        parsed.ledger = df
    for ln in parsed.lines:
        for key, value in ln.amounts.items():
            exact = value * rate
            ln.amounts[key] = exact.quantize(q, ROUND_HALF_UP)
            lost += abs(ln.amounts[key] - exact)
    if lost:
        # L'arrondi de chaque montant déplace l'équilibre d'au plus l'écart cumulé : les
        # contrôles l'admettent, et l'écart est signalé.
        parsed.tolerance = lost
        what = "convertis puis arrondis" if rate != 1 else "arrondis"
        gap = f"{lost:.2f}".replace(".", ",")
        message = f"Montants {what} à {places} décimale(s) : écart d'arrondi cumulé {gap}"
        parsed.avertissements.append({"code": "arrondi", "message": message})


PREPARE.append(convert)
