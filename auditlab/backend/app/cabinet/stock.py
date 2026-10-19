"""Valorisation des stocks (RCO-12) : coût moyen pondéré de la période ou premier entré,
premier sorti, dépréciation à la valeur nette de réalisation."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ZERO = Decimal(0)


def value_article(qty: Decimal, entries: list[dict[str, Any]], method: str) -> Decimal | None:
    """Valeur de la quantité en stock ; `entries` = stock initial et entrées de l'exercice
    (quantité, prix unitaire), dans l'ordre chronologique. None si aucune entrée connue."""
    entries = [e for e in entries if Decimal(e["quantite"]) > 0]
    if not entries:
        return None
    if method == "cmp":
        total_q = sum((Decimal(e["quantite"]) for e in entries), ZERO)
        total_v = sum((Decimal(e["quantite"]) * Decimal(e["prix_unitaire"]) for e in entries), ZERO)
        return qty * total_v / total_q
    # PEPS : le stock restant provient des dernières entrées.
    left, value = qty, ZERO
    for e in reversed(entries):
        take = min(left, Decimal(e["quantite"]))
        value += take * Decimal(e["prix_unitaire"])
        left -= take
        if left <= 0:
            break
    if left > 0:  # plus de stock que d'entrées connues : au plus ancien coût
        value += left * Decimal(entries[0]["prix_unitaire"])
    return value


def valuation(
    inventory: list[dict[str, Any]], movements: list[dict[str, Any]], method: str, q: Decimal
) -> dict[str, Any]:
    by_article: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in sorted(movements, key=lambda m: (m.get("type") != "initial", m.get("date") or "")):
        by_article[m["article"]].append(m)
    rows, missing = [], []
    for item in inventory:
        qty = Decimal(item["quantite"])
        value = value_article(qty, by_article.get(item["article"], []), method)
        if value is None and item.get("cout_unitaire"):
            value = qty * Decimal(item["cout_unitaire"])
        if value is None:
            missing.append(item["article"])
            continue
        value = value.quantize(q, ROUND_HALF_UP)
        nrv = (qty * Decimal(item["vnr"])).quantize(q, ROUND_HALF_UP) if item.get("vnr") else None
        rows.append(
            {
                "article": item["article"],
                "libelle": item.get("libelle"),
                "compte": item["compte"],
                "quantite": str(qty),
                "valeur": str(value),
                "cout_unitaire": str((value / qty).quantize(Decimal("0.0001"))) if qty else "0",
                "valeur_realisation": str(nrv) if nrv is not None else None,
                "depreciation": str(max(ZERO, value - nrv)) if nrv is not None else "0",
            }
        )
    return {"articles": rows, "non_valorises": missing}
