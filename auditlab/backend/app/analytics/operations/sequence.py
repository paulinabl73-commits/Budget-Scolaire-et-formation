"""DAT-11 — ruptures de séquence : numéros manquants et numéros en double.

Avec `groupe` (ex. le journal), chaque valeur du groupe a sa propre numérotation (RCO-08) ;
la table produite indique alors le groupe de chaque rupture. Avec `distinctes` = « oui »,
un numéro répété (lignes d'une même pièce comptable) n'est pas un double."""

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
    group = f"CAST({quote_ident(p['groupe'])} AS VARCHAR)" if p.get("groupe") else "NULL"
    base = (
        f"WITH n AS (SELECT {group} AS grp, {number} AS v FROM t), "  # noqa: S608
        f"d AS (SELECT grp, v, {'1' if p.get('distinctes') == 'oui' else 'count(*)'} AS c "
        "FROM n WHERE v IS NOT NULL GROUP BY grp, v), "
        "g AS (SELECT grp, v, lead(v) OVER (PARTITION BY grp ORDER BY v) AS nxt FROM d) "
    )
    shown = "grp AS groupe, " if p.get("groupe") else ""
    df = evaluate(
        rel,
        base + f"SELECT {shown}'manquant' AS type, v + ? AS debut, "
        "v + (nxt - v - 1) // ? * ? AS fin, (nxt - v - 1) // ? AS nombre FROM g WHERE nxt - v > ? "
        f"UNION ALL SELECT {shown}'double', v, v, c FROM d WHERE c > 1 "
        f"ORDER BY {'groupe, ' if shown else ''}debut, type",
        [step, step, step, step, step],
    )
    stats = evaluate(
        rel,
        base + "SELECT min(v), max(v), (SELECT count(*) FROM n WHERE v IS NULL), "
        "count(DISTINCT grp) FROM d",
    ).row(0)
    low, high, empty, groups = stats
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
            **({"groupes": groups} if p.get("groupe") else {}),
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
            Param("groupe", "colonne", requis=False),
            Param("distinctes", "choix", requis=False, defaut="non", choix=("non", "oui")),
        ),
        run,
    )
)
