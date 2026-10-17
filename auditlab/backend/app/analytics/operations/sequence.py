"""DAT-11 — ruptures de séquence : numéros manquants et numéros en double."""

from typing import Any

from app.analytics.operations.base import Operation, OpResult, Param, register
from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    col, step = p["champ"], int(p["pas"])
    q = quote_ident(col)
    # Numéro : la valeur entière, ou les chiffres de fin d'un texte (« F-2026-0042 » → 42).
    number = (
        f"TRY_CAST(regexp_extract(CAST({q} AS VARCHAR), '(\\d+)$', 1) AS BIGINT)"
        if rel.types[col] == "texte"
        else f"CAST({q} AS BIGINT)"
    )
    base = (
        f"WITH n AS (SELECT {number} AS v FROM t), "  # noqa: S608
        "d AS (SELECT v, count(*) AS c FROM n WHERE v IS NOT NULL GROUP BY v), "
        "g AS (SELECT v, lead(v) OVER (ORDER BY v) AS nxt FROM d) "
    )
    df = evaluate(
        rel,
        base + "SELECT 'manquant' AS type, v + ? AS debut, v + (nxt - v - 1) // ? * ? AS fin, "
        "(nxt - v - 1) // ? AS nombre FROM g WHERE nxt - v > ? "
        "UNION ALL SELECT 'double', v, v, c FROM d WHERE c > 1 ORDER BY debut, type",
        [step, step, step, step, step],
    )
    stats = evaluate(
        rel, base + "SELECT min(v), max(v), (SELECT count(*) FROM n WHERE v IS NULL) FROM d"
    ).row(0)
    low, high, empty = stats
    missing = df.filter(df["type"] == "manquant")
    return OpResult(
        df,
        {
            "minimum": low,
            "maximum": high,
            "attendus": (high - low) // step + 1 if low is not None else 0,
            "manquants": int(missing["nombre"].sum()) if missing.height else 0,
            "plages_manquantes": missing.height,
            "doubles": df.height - missing.height,
            "valeurs_vides": empty,
        },
    )


register(
    Operation(
        "sequence",
        "DAT-11",
        1,
        (
            Param("champ", "colonne", types_colonne=("entier", "texte")),
            Param("pas", "entier", requis=False, defaut=1, minimum=1, maximum=1_000_000),
        ),
        run,
    )
)
