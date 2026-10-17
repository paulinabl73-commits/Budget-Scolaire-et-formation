"""DAT-16 — jointure de deux tables sur des clés (interne, gauche, non appariés)."""

from typing import Any

from app.analytics.operations.base import Operation, OpResult, Param, register, unique_name
from app.analytics.relation import Relation, evaluate_many
from app.analytics.store import quote_ident


def key_condition(rels: list[Relation], pairs: list[dict[str, str]]) -> str:
    """Égalité des clés ; deux types différents sont comparés sous forme de texte."""
    left, right = rels[0].types, rels[1].types
    parts = []
    for pair in pairs:
        a, b = f"a.{quote_ident(pair['gauche'])}", f"b.{quote_ident(pair['droite'])}"
        if left[pair["gauche"]] != right[pair["droite"]]:
            a, b = f"CAST({a} AS VARCHAR)", f"CAST({b} AS VARCHAR)"
        parts.append(f"{a} = {b}")
    return " AND ".join(parts)


def output_columns(rels: list[Relation]) -> list[str]:
    taken = {c["nom"] for c in rels[0].schema}
    cols = [f"a.{quote_ident(c['nom'])}" for c in rels[0].schema]
    for c in rels[1].schema:
        name = unique_name(c["nom"], taken)
        cols.append(f"b.{quote_ident(c['nom'])} AS {quote_ident(name)}")
    return cols


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    on = key_condition(rels, p["cles"])
    cols = ", ".join(output_columns(rels))
    named = {"a": rels[0], "b": rels[1]}
    marked = "(SELECT *, TRUE AS __m FROM {}) {}"
    full = f"{marked.format('a', 'a')} FULL JOIN {marked.format('b', 'b')} ON {on}"
    counts = evaluate_many(
        named,
        "SELECT count(*) FILTER (WHERE a.__m AND b.__m), "
        "count(*) FILTER (WHERE b.__m IS NULL), count(*) FILTER (WHERE a.__m IS NULL) "
        f"FROM {full}",
    ).row(0)
    kind = p["type"]
    if kind == "interne":
        sql = f"SELECT {cols} FROM a JOIN b ON {on} ORDER BY ALL"
    elif kind == "gauche":
        sql = f"SELECT {cols} FROM a LEFT JOIN b ON {on} ORDER BY ALL"
    else:
        sql = (
            f"SELECT CASE WHEN a.__m IS NULL THEN 'table 2' ELSE 'table 1' END AS origine, {cols} "
            f"FROM {full} WHERE a.__m IS NULL OR b.__m IS NULL ORDER BY ALL"
        )
    df = evaluate_many(named, sql)
    return OpResult(
        df,
        {
            "appariees": counts[0],
            "orphelines_gauche": counts[1],
            "orphelines_droite": counts[2],
            "lignes": df.height,
        },
    )


register(
    Operation(
        "jointure",
        "DAT-16",
        2,
        (
            Param("cles", "paires"),
            Param("type", "choix", defaut="interne", choix=("interne", "gauche", "non_apparies")),
        ),
        run,
    )
)
