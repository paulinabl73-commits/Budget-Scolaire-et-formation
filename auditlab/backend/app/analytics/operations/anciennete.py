"""DAT-14 — ancienneté (aging) : montants par tranche de jours à une date de référence."""

from typing import Any

from app.analytics.operations.base import DATES, NUMERIC, Operation, OpResult, Param, register
from app.analytics.operations.tranches import Tranche, by_tranche, summary
from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    d = quote_ident(p["champ_date"])
    days = f"date_diff('day', CAST({d} AS DATE), CAST(? AS DATE))"
    limits = [int(float(x)) for x in p["tranches"]]
    tranches = [Tranche("non échu", None, -1), Tranche(f"0 à {limits[0]} jours", 0, limits[0])]
    for low, high in zip(limits, limits[1:], strict=False):
        tranches.append(Tranche(f"{low + 1} à {high} jours", low + 1, high))
    tranches.append(Tranche(f"plus de {limits[-1]} jours", limits[-1] + 1, None))
    # Rang : 0 si la date est postérieure à la référence, sinon 1 + tranches dépassées.
    index = (
        f"CASE WHEN {days} < 0 THEN 0 ELSE 1 + "
        + " + ".join(f"CAST({days} > {n} AS INTEGER)" for n in limits)
        + " END"
    )
    ref = p["date_reference"]
    amount = quote_ident(p["champ_montant"]) if p.get("champ_montant") else None
    df = by_tranche(
        rel,
        index,
        [ref] * (len(limits) + 1),
        tranches,
        amount,
        f"{d} IS NOT NULL",
        "INTEGER",
        ("jours_min", "jours_max"),
    )
    undated = evaluate(rel, f"SELECT count(*) FROM t WHERE {d} IS NULL").item()
    return OpResult(df, {**summary(df), "sans_date": undated, "non_echu": int(df["nombre"][0])})


register(
    Operation(
        "anciennete",
        "DAT-14",
        1,
        (
            Param("champ_date", "colonne", types_colonne=DATES),
            Param("date_reference", "date"),
            Param("tranches", "nombres", requis=False, defaut=["30", "60", "90", "180", "365"]),
            Param("champ_montant", "colonne", requis=False, types_colonne=NUMERIC),
        ),
        run,
    )
)
