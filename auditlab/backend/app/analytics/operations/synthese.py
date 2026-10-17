"""DAT-13 — synthèse (regroupement et agrégats)."""

from typing import Any

from app.analytics.operations.base import Operation, OpResult, Param, register, unique_name
from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident

SQL = {
    "somme": "sum({})",
    "moyenne": "avg({})",
    "min": "min({})",
    "max": "max({})",
    "nombre": "count({})",
    "distincts": "count(DISTINCT {})",
    "ecart_type": "stddev_samp({})",
}


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    groups = p["groupes"]
    taken = set(groups)
    select = [quote_ident(g) for g in groups]
    select.append(f"count(*) AS {quote_ident(unique_name('nombre', taken))}")
    for agg in p["agregats"] or []:
        name = unique_name(f"{agg['fonction']}_{agg['champ']}", taken)
        select.append(
            f"{SQL[agg['fonction']].format(quote_ident(agg['champ']))} AS {quote_ident(name)}"
        )
    keys = ", ".join(quote_ident(g) for g in groups)
    order = ", ".join(f"{quote_ident(g)} NULLS LAST" for g in groups)
    df = evaluate(rel, f"SELECT {', '.join(select)} FROM t GROUP BY {keys} ORDER BY {order}")
    return OpResult(df, {"groupes": df.height, "lignes": int(df[df.columns[len(groups)]].sum())})


register(
    Operation(
        "synthese",
        "DAT-13",
        1,
        (Param("groupes", "colonnes"), Param("agregats", "agregats", requis=False, defaut=[])),
        run,
    )
)
