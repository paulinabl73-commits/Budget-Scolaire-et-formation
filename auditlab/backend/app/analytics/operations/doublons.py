"""DAT-10 — doublons sur des champs clés, correspondance exacte ou approchée (Jaro-Winkler)."""

from typing import Any

import polars as pl

from app.analytics.operations.base import (
    TEXT,
    AnalysisError,
    Operation,
    OpResult,
    Param,
    register,
    unique_name,
)
from app.analytics.relation import Relation, evaluate
from app.analytics.store import connect, quote_ident

MAX_PAIRS = 50_000_000

# Normalisation des textes comparés : casse, accents, ponctuation et espaces multiples.
NORMALIZE = (
    "trim(regexp_replace(lower(strip_accents(CAST({} AS VARCHAR))), '[^a-z0-9]+', ' ', 'g'))"
)


def exact(rel: Relation, keys: list[str]) -> OpResult:
    taken = {c["nom"] for c in rel.schema}
    groupe, nombre = unique_name("groupe", taken), unique_name("nb_dans_groupe", taken)
    k = ", ".join(quote_ident(c) for c in keys)
    sql = (
        f"SELECT dense_rank() OVER (ORDER BY {k}) AS {quote_ident(groupe)}, "  # noqa: S608
        f"__nb AS {quote_ident(nombre)}, * EXCLUDE (__nb) "
        f"FROM (SELECT *, count(*) OVER (PARTITION BY {k}) AS __nb FROM t) WHERE __nb > 1 "
        "ORDER BY ALL"
    )
    df = evaluate(rel, sql)
    groups = df[groupe].n_unique() if df.height else 0
    return OpResult(df, {"groupes": groups, "lignes_en_double": df.height})


def approximate(rel: Relation, keys: list[str], threshold: float) -> OpResult:
    types = rel.types
    fuzzy = [c for c in keys if types[c] in TEXT]
    if not fuzzy:
        raise AnalysisError("La correspondance approchée exige au moins un champ texte")
    strict = [c for c in keys if c not in fuzzy]
    df = evaluate(rel, "SELECT * FROM t").with_row_index("__id")
    if df.height**2 / 2 > MAX_PAIRS * 50:
        raise AnalysisError("Table trop volumineuse pour une comparaison approchée ; filtrez-la")
    norm = [f"{NORMALIZE.format(quote_ident(c))} AS __n{i}" for i, c in enumerate(fuzzy)]
    strict_cols = ", ".join(quote_ident(c) for c in strict)
    keys_sql = ", ".join(["__id", *norm, *([strict_cols] if strict else [])])
    conds = ["a.__id < b.__id", "left(a.__n0, 1) = left(b.__n0, 1)"]
    conds += [f"a.{quote_ident(c)} = b.{quote_ident(c)}" for c in strict]
    conds += [f"a.__n{i} IS NOT NULL AND a.__n{i} <> ''" for i in range(len(fuzzy))]
    scores = [f"jaro_winkler_similarity(a.__n{i}, b.__n{i})" for i in range(len(fuzzy))]
    score = scores[0] if len(scores) == 1 else f"least({', '.join(scores)})"
    with connect() as con:
        con.register("src", df.select(["__id", *keys]))
        con.execute(f"CREATE TEMP TABLE k AS SELECT {keys_sql} FROM src")  # noqa: S608
        compared = con.execute(
            f"SELECT count(*) FROM k a JOIN k b ON {' AND '.join(conds)}"  # noqa: S608
        ).fetchone()[0]
        if compared > MAX_PAIRS:
            raise AnalysisError("Trop de paires à comparer ; ajoutez un champ clé exact")
        pairs = con.execute(
            f"SELECT a.__id, b.__id, {score} AS s FROM k a JOIN k b ON {' AND '.join(conds)} "  # noqa: S608
            f"WHERE {score} >= ? ORDER BY 1, 2",
            [threshold],
        ).fetchall()
    # Groupes = composantes connexes des paires similaires (union-find).
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    best: dict[int, float] = {}
    for a, b, s in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
        best[a], best[b] = max(best.get(a, 0), s), max(best.get(b, 0), s)
    roots = {i: find(i) for i in best}
    numbering = {r: n for n, r in enumerate(sorted(set(roots.values())), start=1)}
    taken = set(df.columns)
    groupe, score_col = unique_name("groupe", taken), unique_name("similarite", taken)
    ids = sorted(roots, key=lambda i: (numbering[roots[i]], i))
    meta = pl.DataFrame(
        {
            "__id": pl.Series(ids, dtype=df["__id"].dtype),
            groupe: [numbering[roots[i]] for i in ids],
            score_col: [round(best[i], 4) for i in ids],
        }
    )
    out = meta.join(df, on="__id", how="left", maintain_order="left").drop("__id")
    return OpResult(
        out,
        {"groupes": len(numbering), "lignes_en_double": out.height, "paires_comparees": compared},
    )


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    if p["mode"] == "approchee":
        return approximate(rels[0], p["cles"], float(p["seuil"]))
    return exact(rels[0], p["cles"])


register(
    Operation(
        "doublons",
        "DAT-10",
        1,
        (
            Param("cles", "colonnes"),
            Param("mode", "choix", defaut="exacte", choix=("exacte", "approchee")),
            Param("seuil", "nombre", requis=False, defaut="0.9", minimum=0.5, maximum=1),
        ),
        run,
    )
)
