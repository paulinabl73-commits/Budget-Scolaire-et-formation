"""Lettrage et justification des comptes de tiers, balance âgée et dépréciation des créances
(REV-18), à partir du grand livre N du dossier.

- Lettrage : celui du logiciel (colonne « lettrage ») quand il existe ; un code dont les lignes
  ne s'annulent pas est signalé et ses lignes restent ouvertes. Sans lettrage, un lettrage
  automatique rapproche, compte par compte, un crédit d'un débit de même montant (le plus
  ancien d'abord).
- Justification : les lignes non lettrées d'un compte doivent expliquer son solde de clôture.
- Balance âgée : par tiers (à défaut par compte), les crédits non lettrés (règlements non
  affectés, avoirs) sont imputés sur les débits les plus anciens ; le reste est classé par
  ancienneté à la date de clôture.
- Dépréciation : taux de la grille selon l'ancienneté, appliqué au montant hors taxes.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import polars as pl

ZERO = Decimal(0)


@dataclass
class Item:
    compte: str
    tiers: str | None
    date: dt.date | None
    piece: str | None
    libelle: str | None
    net: Decimal  # débit − crédit


@dataclass
class AccountState:
    compte: str
    lettrees: int = 0
    ouvertes: list[Item] = field(default_factory=list)
    mode: str = "automatique"
    anomalies: list[str] = field(default_factory=list)

    @property
    def solde_ouvert(self) -> Decimal:
        return sum((i.net for i in self.ouvertes), ZERO)


def _items(df: pl.DataFrame) -> list[Item]:
    cols = set(df.columns)
    out = []
    for r in df.iter_rows(named=True):
        out.append(
            Item(
                r["compte"],
                r.get("tiers") if "tiers" in cols else None,
                r.get("date"),
                r.get("piece") if "piece" in cols else None,
                r.get("libelle") if "libelle" in cols else None,
                Decimal(r["debit"] or 0) - Decimal(r["credit"] or 0),
            )
        )
    return out


def match(df: pl.DataFrame, roots: list[str]) -> dict[str, AccountState]:
    """Lettrage des comptes de tiers du grand livre (colonnes compte, debit, credit, date)."""
    keep = pl.any_horizontal([pl.col("compte").str.starts_with(r) for r in roots])
    tiers = df.filter(keep).sort(["compte", "date"], nulls_last=True)
    has_codes = "lettrage" in tiers.columns
    states: dict[str, AccountState] = {}
    for (compte,), part in tiers.group_by(["compte"], maintain_order=True):
        state = states.setdefault(compte, AccountState(compte))
        codes = part["lettrage"].to_list() if has_codes else [None] * part.height
        items = _items(part)
        if any(c not in (None, "") for c in codes):
            state.mode = "fourni"
            groups: dict[str, list[Item]] = defaultdict(list)
            for item, code in zip(items, codes, strict=True):
                if code in (None, ""):
                    state.ouvertes.append(item)
                else:
                    groups[str(code)].append(item)
            for code, lines in groups.items():
                if sum((i.net for i in lines), ZERO) == 0:
                    state.lettrees += len(lines)
                else:
                    state.anomalies.append(f"Lettrage « {code} » déséquilibré")
                    state.ouvertes.extend(lines)
        else:
            debits = [i for i in items if i.net > 0]
            for credit in (i for i in items if i.net < 0):
                found = next((d for d in debits if d.net == -credit.net), None)
                if found is None:
                    state.ouvertes.append(credit)
                else:
                    debits.remove(found)
                    state.lettrees += 2
            state.ouvertes.extend(debits)
        state.ouvertes.sort(key=lambda i: (i.date or dt.date.min, i.piece or ""))
    return states


def tranches(grid: list[list[float]]) -> list[dict[str, Any]]:
    """Tranches d'ancienneté issues de la grille [[jours_min, taux %], …]."""
    rows = sorted(([int(a), Decimal(str(b))] for a, b in grid), key=lambda x: x[0])
    out = []
    for i, (low, rate) in enumerate(rows):
        high = rows[i + 1][0] - 1 if i + 1 < len(rows) else None
        label = f"{low} à {high} jours" if high is not None else f"{low} jours et plus"
        out.append({"jours_min": low, "jours_max": high, "taux": rate, "libelle": label})
    return out


def aging(
    states: dict[str, AccountState],
    closing: dt.date,
    grid: list[list[float]],
    vat_pct: Decimal | None,
    places: int,
) -> dict[str, Any]:
    """Balance âgée des créances ouvertes et dépréciation requise selon la grille."""
    bands = tranches(grid)
    q = Decimal(1).scaleb(-places)
    by_party: dict[str, list[Item]] = defaultdict(list)
    for state in states.values():
        for item in state.ouvertes:
            by_party[item.tiers or item.compte].append(item)
    rows, totals = [], [ZERO] * len(bands)
    required = ZERO
    for party, items in sorted(by_party.items()):
        debits = sorted((i for i in items if i.net > 0), key=lambda i: i.date or dt.date.min)
        credit = -sum((i.net for i in items if i.net < 0), ZERO)
        amounts = [ZERO] * len(bands)
        provision = ZERO
        for d in debits:
            remaining = d.net - min(credit, d.net)
            credit -= d.net - remaining
            if remaining <= 0:
                continue
            age = (closing - d.date).days if d.date else 0
            k = max((i for i, b in enumerate(bands) if age >= b["jours_min"]), default=0)
            amounts[k] += remaining
            base = remaining / (1 + vat_pct / 100) if vat_pct else remaining
            provision += base * bands[k]["taux"] / 100
        provision = provision.quantize(q, ROUND_HALF_UP)
        totals = [a + b for a, b in zip(totals, amounts, strict=True)]
        required += provision
        rows.append(
            {
                "tiers": party,
                "solde": str((sum(amounts, ZERO) - credit).quantize(q)),
                "tranches": [str(a.quantize(q)) for a in amounts],
                "depreciation": str(provision),
                "credit_non_impute": str(credit.quantize(q)),
            }
        )
    return {
        "tranches": [{**b, "taux": str(b["taux"])} for b in bands],
        "tiers": rows,
        "totaux": [str(t.quantize(q)) for t in totals],
        "depreciation_requise": str(required),
    }
