"""Rapprochements bancaires (REV-20) : lecture de l'état des suspens et contrôles.

Fichier CSV ou Excel, une ligne par suspens : date, libellé, référence, origine (« relevé »
pour une opération passée par la banque seule, « comptabilité » pour une écriture non encore
passée par la banque) et montant à ajouter au solde du relevé pour retrouver le solde
comptable. Contrôles : solde comptable du rapprochement égal à la balance, montant non
rapproché nul, suspens anciens, opérations du relevé à comptabiliser, concordance avec la
confirmation bancaire.
"""

import datetime as dt
from decimal import Decimal
from typing import Any

from app.revision.balances import ImportError_, normalize, parse_amount, parse_date, read_rows

FIELDS = {
    "date": ("date", "date operation", "date valeur", "date de l operation"),
    "libelle": ("libelle", "designation", "intitule", "description"),
    "reference": ("reference", "piece", "n piece", "numero", "n cheque", "cheque"),
    "origine": ("origine", "cote", "source", "nature"),
    "montant": ("montant", "montant a ajouter", "somme"),
}
ORIGINS = {
    "releve": "releve",
    "banque": "releve",
    "bank": "releve",
    "comptabilite": "comptabilite",
    "compta": "comptabilite",
    "livres": "comptabilite",
    "entreprise": "comptabilite",
}


def _header(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows[:30]):
        headers = [normalize(h) for h in row]
        cols = {f: headers.index(n) for f, names in FIELDS.items() for n in names if n in headers}
        if {"montant", "origine"} <= set(cols):
            return index, cols
    raise ImportError_("En-tête introuvable : colonnes « origine » et « montant » attendues")


def parse_items(content: bytes, filename: str) -> list[dict[str, Any]]:
    rows = read_rows(content, filename)
    index, cols = _header(rows)
    items = []
    for row in rows[index + 1 :]:

        def get(f: str, row: list[Any] = row) -> Any:
            i = cols.get(f)
            return row[i] if i is not None and i < len(row) else None

        if get("montant") in (None, "") and get("origine") in (None, ""):
            continue
        origin = ORIGINS.get(normalize(get("origine")).split(" ")[0] if get("origine") else "")
        if origin is None:
            raise ImportError_(f"Origine inconnue « {get('origine')} » (relevé ou comptabilité)")
        items.append(
            {
                "date": parse_date(get("date")),
                "libelle": str(get("libelle") or "")[:300] or None,
                "reference": str(get("reference") or "")[:60] or None,
                "origine": origin,
                "montant": parse_amount(get("montant")),
            }
        )
    return items


def controls(
    statement: Decimal,
    book: Decimal,
    items: list[Any],
    statement_date: dt.date,
    closing: dt.date,
    old_days: int,
    trivial: Decimal,
    confirmed: Decimal | None,
) -> dict[str, Any]:
    unreconciled = book - statement - sum((i.montant for i in items), Decimal(0))
    limit = closing - dt.timedelta(days=old_days)
    old = [i for i in items if i.date is not None and i.date < limit]
    bank_only = sum((i.montant for i in items if i.origine == "releve"), Decimal(0))
    anomalies, warnings = [], []
    if unreconciled:
        amount = f"{unreconciled:,.2f}".replace(",", " ").replace(".", ",")
        anomalies.append(f"Montant non rapproché : {amount}")
    if statement_date != closing:
        warnings.append(f"Relevé arrêté au {statement_date:%d/%m/%Y}, et non à la clôture")
    if old:
        warnings.append(f"{len(old)} suspens antérieur(s) au {limit:%d/%m/%Y}")
    if abs(bank_only) > trivial:
        warnings.append("Opérations passées par la banque seule, à comptabiliser à la clôture")
    if confirmed is not None and confirmed != statement:
        anomalies.append("Solde du relevé différent du solde confirmé par la banque")
    return {
        "non_rapproche": unreconciled,
        "suspens_anciens": len(old),
        "operations_releve": bank_only,
        "anomalies": anomalies,
        "avertissements": warnings,
    }
