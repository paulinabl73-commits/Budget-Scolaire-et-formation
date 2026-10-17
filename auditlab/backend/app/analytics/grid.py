"""Lecture paginée d'une table pour la grille (DAT-07) : tri, filtres, recherche, colonnes.

Le modèle de filtres est celui d'AG Grid ; il est traduit en SQL paramétré. Seules les
colonnes du schéma sont acceptées, et toujours citées.
"""

import datetime as dt
from decimal import Decimal
from typing import Any

from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident


class GridError(ValueError):
    pass


_COMPARISONS = {
    "equals": "=",
    "notEqual": "<>",
    "lessThan": "<",
    "lessThanOrEqual": "<=",
    "greaterThan": ">",
    "greaterThanOrEqual": ">=",
}


def _value(kind: str, raw: Any) -> Any:
    if raw is None:
        raise GridError("Valeur de filtre manquante")
    if kind == "number":
        try:
            return Decimal(str(raw))
        except ArithmeticError as exc:
            raise GridError("Nombre invalide dans le filtre") from exc
    if kind == "date":
        try:
            return dt.date.fromisoformat(str(raw)[:10])
        except ValueError as exc:
            raise GridError("Date invalide dans le filtre") from exc
    return str(raw)


def _condition(col: str, model: dict[str, Any], params: list[Any]) -> str:
    if "conditions" in model:
        op = " OR " if str(model.get("operator", "AND")).upper() == "OR" else " AND "
        parts = [_condition(col, m, params) for m in model["conditions"][:5]]
        return "(" + op.join(parts) + ")"
    kind = model.get("filterType", "text")
    ftype = model.get("type", "contains")
    q = quote_ident(col)
    if ftype == "blank":
        return f"({q} IS NULL)" if kind != "text" else f"(coalesce(CAST({q} AS VARCHAR), '') = '')"
    if ftype == "notBlank":
        return (
            f"({q} IS NOT NULL)"
            if kind != "text"
            else f"(coalesce(CAST({q} AS VARCHAR), '') <> '')"
        )
    if kind == "date":
        first, second = model.get("dateFrom"), model.get("dateTo")
        cast = "date"
    else:
        first, second = model.get("filter"), model.get("filterTo")
        cast = kind
    if kind == "text":
        text = f"lower(CAST({q} AS VARCHAR))"
        params.append(_value("text", first).lower())
        sql = {
            "contains": f"contains({text}, ?)",
            "notContains": f"NOT coalesce(contains({text}, ?), FALSE)",
            "equals": f"{text} = ?",
            "notEqual": f"coalesce({text} <> ?, TRUE)",
            "startsWith": f"starts_with({text}, ?)",
            "endsWith": f"ends_with({text}, ?)",
        }.get(ftype)
        if sql is None:
            raise GridError(f"Filtre texte inconnu « {ftype} »")
        return f"({sql})"
    if kind not in ("number", "date"):
        raise GridError(f"Type de filtre inconnu « {kind} »")
    target = f"CAST({q} AS DATE)" if cast == "date" else q
    if ftype == "inRange":
        params.extend([_value(cast, first), _value(cast, second)])
        return f"({target} BETWEEN ? AND ?)"
    if ftype not in _COMPARISONS:
        raise GridError(f"Filtre inconnu « {ftype} »")
    params.append(_value(cast, first))
    return f"({target} {_COMPARISONS[ftype]} ?)"


def where_clause(
    schema: list[dict[str, Any]], filters: dict[str, Any], search: str | None
) -> tuple[str, list[Any]]:
    names = {c["nom"] for c in schema}
    parts: list[str] = []
    params: list[Any] = []
    for col, model in filters.items():
        if col not in names:
            raise GridError(f"Colonne inconnue « {col} »")
        parts.append(_condition(col, model, params))
    if search and search.strip():
        needle = search.strip().lower()
        ors = []
        for c in schema:
            ors.append(f"contains(lower(CAST({quote_ident(c['nom'])} AS VARCHAR)), ?)")
            params.append(needle)
        parts.append("(" + " OR ".join(ors) + ")")
    return (" WHERE " + " AND ".join(parts)) if parts else "", params


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def read_page(
    rel: Relation,
    *,
    offset: int,
    limit: int,
    sort: list[dict[str, str]],
    filters: dict[str, Any],
    search: str | None,
    columns: list[str] | None,
    with_total: bool,
) -> dict[str, Any]:
    names = [c["nom"] for c in rel.schema]
    selected = columns or names
    unknown = [c for c in selected + [s["colonne"] for s in sort] if c not in names]
    if unknown:
        raise GridError(f"Colonne inconnue « {unknown[0]} »")
    where, params = where_clause(rel.schema, filters, search)
    order = ", ".join(
        f"{quote_ident(s['colonne'])} {'DESC' if s.get('sens') == 'desc' else 'ASC'} NULLS LAST"
        for s in sort
    )
    cols = ", ".join(quote_ident(c) for c in selected)
    sql = f"SELECT {cols} FROM t{where}"  # noqa: S608 - colonnes vérifiées, valeurs en paramètres
    if order:
        sql += f" ORDER BY {order}"
    sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    df = evaluate(rel, sql, params)
    total = None
    if with_total:
        total = evaluate(rel, f"SELECT count(*) FROM t{where}", params).item()  # noqa: S608
    return {
        "colonnes": selected,
        "lignes": [[jsonable(v) for v in row] for row in df.iter_rows()],
        "total": total,
    }


def field_stats(
    rel: Relation, column: str, filters: dict[str, Any], search: str | None
) -> dict[str, Any]:
    """Statistiques de champ (DAT-08), sur toute la table ou sur la sélection filtrée."""
    types = rel.types
    if column not in types:
        raise GridError(f"Colonne inconnue « {column} »")
    kind = types[column]
    where, params = where_clause(rel.schema, filters, search)
    q = quote_ident(column)
    numeric = kind in ("entier", "decimal")
    exprs = [
        "count(*)",
        f"count({q})",
        f"count(DISTINCT {q})",
        f"min({q})",
        f"max({q})",
    ]
    if numeric:
        exprs += [
            f"sum({q})",
            f"avg({q})",
            f"stddev_samp({q})",
            f"count(*) FILTER (WHERE {q} > 0)",
            f"count(*) FILTER (WHERE {q} < 0)",
            f"count(*) FILTER (WHERE {q} = 0)",
        ]
    row = evaluate(rel, f"SELECT {', '.join(exprs)} FROM t{where}", params).row(0)  # noqa: S608
    lignes, valeurs, distinctes, low, high = row[:5]
    stats: dict[str, Any] = {
        "colonne": column,
        "type": kind,
        "lignes": lignes,
        "nombre": valeurs,
        "nulles": lignes - valeurs,
        "distinctes": distinctes,
        "min": jsonable(low),
        "max": jsonable(high),
    }
    if numeric:
        total, mean, std, pos, neg, zero = row[5:]
        stats.update(
            total=str(jsonable(total)) if total is not None else "0",
            moyenne=float(mean) if mean is not None else None,
            ecart_type=float(std) if std is not None else None,
            positives=pos,
            negatives=neg,
            zeros=zero,
        )
    top = evaluate(
        rel,
        f"SELECT {q} AS v, count(*) AS n FROM t{where} GROUP BY 1 ORDER BY n DESC, v NULLS LAST LIMIT 10",  # noqa: S608, E501
        params,
    )
    stats["frequentes"] = [{"valeur": jsonable(v), "nombre": n} for v, n in top.iter_rows()]
    return stats
