"""Relation SQL d'une table, quelle que soit sa nature (import, vue, analyse).

Une vue (DAT-06) n'a pas de fichier : sa relation est celle de sa table parente, augmentée de
ses champs calculés. Les grilles, statistiques et analyses lisent toutes par ce module.
"""

from dataclasses import dataclass, field
from typing import Any

import duckdb
import polars as pl
from sqlalchemy.orm import Session

from app.analytics.expr import ExprError, compile_expression
from app.analytics.store import connect, dtype_name, parquet_ref, quote_ident
from app.models.data import Dataset, DatasetKind, DatasetStatus

MAX_DEPTH = 20


class RelationError(ValueError):
    pass


@dataclass
class Relation:
    sql: str
    params: list[Any] = field(default_factory=list)
    schema: list[dict[str, Any]] = field(default_factory=list)

    @property
    def types(self) -> dict[str, str]:
        return {c["nom"]: c["type"] for c in self.schema}


def extend(base: Relation, champs: list[dict[str, str]]) -> Relation:
    """Ajoute des champs calculés ; chacun peut utiliser les précédents."""
    rel = base
    for champ in champs:
        try:
            compiled = compile_expression(champ["expression"], rel.types)
        except ExprError as exc:
            raise ExprError(f"{champ['nom']} : {exc}", exc.position) from exc
        sql = f"SELECT *, {compiled.sql} AS {quote_ident(champ['nom'])} FROM ({rel.sql})"  # noqa: S608
        rel = Relation(sql, rel.params + compiled.params, rel.schema)
        rel.schema = describe(rel)
    return rel


def describe(rel: Relation) -> list[dict[str, Any]]:
    with connect() as con:
        try:
            df = con.execute(f"SELECT * FROM ({rel.sql}) LIMIT 0", rel.params).pl()  # noqa: S608
        except duckdb.Error as exc:
            raise RelationError(clean_error(exc)) from exc
    return [{"nom": n, "type": dtype_name(t), "dtype": str(t)} for n, t in df.schema.items()]


def relation(db: Session, ds: Dataset, depth: int = 0) -> Relation:
    if ds.statut != DatasetStatus.PRET.value:
        raise RelationError("La table n'est pas prête")
    if depth > MAX_DEPTH:
        raise RelationError("Trop de vues imbriquées")
    if ds.kind == DatasetKind.VUE.value:
        parent = db.get(Dataset, ds.parent_dataset_id)
        base = relation(db, parent, depth + 1)
        rel = extend(base, ds.definition.get("champs", []))
        return Relation(rel.sql, rel.params, ds.schema or rel.schema)
    return Relation(f"SELECT * FROM {parquet_ref(ds.chemin_parquet)}", [], ds.schema)  # noqa: S608


def clean_error(exc: Exception) -> str:
    """Message DuckDB lisible, sans le détail interne de la requête."""
    text = str(exc).split("\n")[0]
    for prefix in (
        "Conversion Error: ",
        "Binder Error: ",
        "Invalid Input Error: ",
        "Out of Range Error: ",
    ):
        text = text.removeprefix(prefix)
    return text[:300]


def evaluate(rel: Relation, sql: str, params: list[Any] | None = None) -> pl.DataFrame:
    """Exécute une requête sur la relation, exposée sous le nom `t`."""
    return evaluate_many({"t": rel}, sql, params)


def evaluate_many(
    rels: dict[str, Relation], sql: str, params: list[Any] | None = None
) -> pl.DataFrame:
    """Exécute une requête sur plusieurs relations, exposées sous les noms donnés (a, b…)."""
    ctes = ", ".join(f"{name} AS ({rel.sql})" for name, rel in rels.items())
    values = [v for rel in rels.values() for v in rel.params] + (params or [])
    with connect() as con:
        try:
            return con.execute(f"WITH {ctes} {sql}", values).pl()  # noqa: S608
        except duckdb.Error as exc:
            raise RelationError(clean_error(exc)) from exc
