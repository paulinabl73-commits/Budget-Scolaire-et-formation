"""Répartition par tranches, commune à la stratification (DAT-12) et à l'ancienneté (DAT-14)."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import polars as pl

from app.analytics.relation import Relation, evaluate


@dataclass
class Tranche:
    libelle: str
    inf: Any
    sup: Any


def by_tranche(
    rel: Relation,
    index_sql: str,
    index_params: list[Any],
    tranches: list[Tranche],
    amount_sql: str | None,
    where: str,
    cast: str,
    names: tuple[str, str] = ("borne_inf", "borne_sup"),
) -> pl.DataFrame:
    """Nombre, total et parts par tranche ; toutes les tranches figurent, même vides.

    `index_sql` donne le rang de tranche (0, 1…) de chaque ligne retenue par `where`.
    """
    values = ", ".join(
        f"({i}, CAST(? AS VARCHAR), CAST(? AS {cast}), CAST(? AS {cast}))"
        for i in range(len(tranches))
    )
    params: list[Any] = [v for tr in tranches for v in (tr.libelle, tr.inf, tr.sup)]
    amount = amount_sql or "NULL"
    total_cols = (
        ", coalesce(a.s, 0) AS total, "
        "round(100 * coalesce(a.s, 0) / nullif(tot.ts, 0), 2) AS part_total"
        if amount_sql
        else ""
    )
    sql = (
        f"WITH b(idx, tranche, inf, sup) AS (VALUES {values}), "
        f"a AS (SELECT {index_sql} AS idx, count(*) AS n, sum({amount}) AS s "
        f"FROM t WHERE {where} GROUP BY 1), "
        "tot AS (SELECT sum(n) AS tn, sum(s) AS ts FROM a) "
        f"SELECT b.tranche, b.inf AS {names[0]}, b.sup AS {names[1]}, "
        "coalesce(a.n, 0) AS nombre, "
        "round(100.0 * coalesce(a.n, 0) / nullif(tot.tn, 0), 2) AS part_nombre"
        f"{total_cols} FROM b LEFT JOIN a USING (idx) CROSS JOIN tot ORDER BY b.idx"
    )
    return evaluate(rel, sql, params + index_params)


def label_number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def summary(df: pl.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"lignes": int(df["nombre"].sum())}
    if "total" in df.columns:
        total = df["total"].sum()
        out["total_general"] = format(total, "f") if isinstance(total, Decimal) else total
    return out
