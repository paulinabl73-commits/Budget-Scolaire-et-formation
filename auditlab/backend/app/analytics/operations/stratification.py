"""DAT-12 — stratification : nombre et total par tranche de valeurs."""

from decimal import Decimal
from typing import Any

from app.analytics.operations.base import NUMERIC, Operation, OpResult, Param, register
from app.analytics.operations.tranches import Tranche, by_tranche, label_number, summary
from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    q = quote_ident(p["champ"])
    bounds = [Decimal(b) for b in p["bornes"]]
    tranches = [Tranche(f"moins de {label_number(bounds[0])}", None, str(bounds[0]))]
    for low, high in zip(bounds, bounds[1:], strict=False):
        tranches.append(
            Tranche(f"de {label_number(low)} à moins de {label_number(high)}", str(low), str(high))
        )
    tranches.append(Tranche(f"{label_number(bounds[-1])} et plus", str(bounds[-1]), None))
    # Rang de tranche = nombre de bornes inférieures ou égales à la valeur.
    index = " + ".join(f"CAST({q} >= CAST(? AS DECIMAL(38, 6)) AS INTEGER)" for _ in bounds)
    df = by_tranche(
        rel, index, [str(b) for b in bounds], tranches, q, f"{q} IS NOT NULL", "DECIMAL(38, 6)"
    )
    empty = evaluate(rel, f"SELECT count(*) FROM t WHERE {q} IS NULL").item()
    return OpResult(df, {**summary(df), "valeurs_vides": empty})


register(
    Operation(
        "stratification",
        "DAT-12",
        1,
        (Param("champ", "colonne", types_colonne=NUMERIC), Param("bornes", "nombres")),
        run,
    )
)
