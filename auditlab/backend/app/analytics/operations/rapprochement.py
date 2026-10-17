"""DAT-17 — rapprochement de deux tables par clé : écarts de montant et lignes orphelines."""

from decimal import Decimal
from typing import Any

from app.analytics.operations.base import NUMERIC, Operation, OpResult, Param, register, unique_name
from app.analytics.operations.jointure import key_condition
from app.analytics.relation import Relation, evaluate_many
from app.analytics.store import quote_ident


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    pairs = p["cles"]
    left_keys = [quote_ident(k["gauche"]) for k in pairs]
    right_keys = [quote_ident(k["droite"]) for k in pairs]
    ma, mb = quote_ident(p["montant_gauche"]), quote_ident(p["montant_droite"])
    on = key_condition(rels, pairs)
    taken: set[str] = set()
    key_names = [quote_ident(unique_name(k["gauche"], taken)) for k in pairs]
    keys_out = ", ".join(
        f"coalesce(CAST(a.{lk} AS VARCHAR), CAST(b.{rk} AS VARCHAR)) AS {name}"
        if rels[0].types[pair["gauche"]] != rels[1].types[pair["droite"]]
        else f"coalesce(a.{lk}, b.{rk}) AS {name}"
        for lk, rk, name, pair in zip(left_keys, right_keys, key_names, pairs, strict=True)
    )
    statut = (
        "CASE WHEN a.n IS NULL THEN 'orphelin table 2' WHEN b.n IS NULL THEN 'orphelin table 1' "
        "WHEN abs(coalesce(a.s, 0) - coalesce(b.s, 0)) <= CAST(? AS DECIMAL(38, 6)) "
        "THEN 'concordant' ELSE 'écart' END"
    )
    sql = (
        f"WITH ga AS (SELECT {', '.join(left_keys)}, count(*) AS n, sum({ma}) AS s "
        f"FROM a GROUP BY ALL), "
        f"gb AS (SELECT {', '.join(right_keys)}, count(*) AS n, sum({mb}) AS s "
        f"FROM b GROUP BY ALL) "
        f"SELECT {keys_out}, coalesce(a.n, 0) AS nb_table_1, coalesce(a.s, 0) AS montant_table_1, "
        "coalesce(b.n, 0) AS nb_table_2, coalesce(b.s, 0) AS montant_table_2, "
        "coalesce(a.s, 0) - coalesce(b.s, 0) AS ecart, "
        f"{statut} AS statut FROM ga a FULL JOIN gb b ON {on} ORDER BY ALL"
    )
    df = evaluate_many({"a": rels[0], "b": rels[1]}, sql, [p["tolerance"]])
    by_status = dict(df.group_by("statut").len().rows()) if df.height else {}

    def total(col: str) -> str:
        value = df[col].sum() if df.height else 0
        return format(value, "f") if isinstance(value, Decimal) else str(value)

    return OpResult(
        df,
        {
            "concordants": by_status.get("concordant", 0),
            "ecarts": by_status.get("écart", 0),
            "orphelines_gauche": by_status.get("orphelin table 1", 0),
            "orphelines_droite": by_status.get("orphelin table 2", 0),
            "total_gauche": total("montant_table_1"),
            "total_droite": total("montant_table_2"),
            "ecart_total": total("ecart"),
        },
    )


register(
    Operation(
        "rapprochement",
        "DAT-17",
        2,
        (
            Param("cles", "paires"),
            Param("montant_gauche", "colonne", types_colonne=NUMERIC),
            Param("montant_droite", "colonne", table=1, types_colonne=NUMERIC),
            Param("tolerance", "nombre", requis=False, defaut="0", minimum=0),
        ),
        run,
    )
)
