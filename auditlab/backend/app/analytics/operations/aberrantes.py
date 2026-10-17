"""DAT-18 — valeurs aberrantes par score z ou par écart interquartile (méthode de Tukey)."""

from typing import Any

from app.analytics.operations.base import NUMERIC, Operation, OpResult, Param, register, unique_name
from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident

DEFAULTS = {"zscore": 3.0, "iqr": 1.5}


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    q = quote_ident(p["champ"])
    x = f"CAST({q} AS DOUBLE)"
    method = p["methode"]
    k = float(p["seuil"]) if p.get("seuil") is not None else DEFAULTS[method]
    score_name = quote_ident(unique_name("score", {c["nom"] for c in rel.schema}))
    if method == "zscore":
        mean, std = evaluate(rel, f"SELECT avg({x}), stddev_samp({x}) FROM t").row(0)
        info = {"moyenne": mean, "ecart_type": std}
        if not std:
            return OpResult(evaluate(rel, f"SELECT *, 0.0 AS {score_name} FROM t WHERE FALSE"),
                            {**info, "aberrantes": 0})  # fmt: skip
        score = f"({x} - ?) / ?"
        params = [mean, std]
        where = f"abs({score}) > ?"
        params_where = [mean, std, k]
        low, high = mean - k * std, mean + k * std
    else:
        q1, q3 = evaluate(
            rel, f"SELECT quantile_cont({x}, 0.25), quantile_cont({x}, 0.75) FROM t"
        ).row(0)
        iqr = (q3 or 0) - (q1 or 0)
        low, high = (q1 or 0) - k * iqr, (q3 or 0) + k * iqr
        info = {"q1": q1, "q3": q3}
        # Score : distance à la borne franchie, en nombre d'écarts interquartiles.
        score = f"CASE WHEN {x} > ? THEN ({x} - ?) / nullif(?, 0) ELSE (? - {x}) / nullif(?, 0) END"
        params = [q3, q3, iqr, q1, iqr]
        where = f"({x} < ? OR {x} > ?)"
        params_where = [low, high]
    ties = ", ".join(quote_ident(c["nom"]) for c in rel.schema)
    df = evaluate(
        rel,
        f"SELECT * FROM (SELECT *, round({score}, 4) AS {score_name} FROM t WHERE {where}) "
        f"ORDER BY abs({score_name}) DESC, {ties}",
        params + params_where,
    )
    return OpResult(
        df,
        {
            **info,
            "borne_basse": round(low, 6),
            "borne_haute": round(high, 6),
            "aberrantes": df.height,
        },
    )


register(
    Operation(
        "aberrantes",
        "DAT-18",
        1,
        (
            Param("champ", "colonne", types_colonne=NUMERIC),
            Param("methode", "choix", defaut="zscore", choix=("zscore", "iqr")),
            Param("seuil", "nombre", requis=False, minimum=0.1, maximum=100),
        ),
        run,
    )
)
