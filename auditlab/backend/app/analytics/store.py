"""Stockage des tables en Parquet, en lecture seule (DAT-05).

Une table importée ou produite par une analyse est écrite une seule fois, dans un fichier
neuf, puis rendue non modifiable (droits 0444). Aucune opération ne réécrit une table : toute
transformation produit une nouvelle table (lignée, DAT-24).
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from app.config import get_settings


def data_dir() -> Path:
    path = Path(get_settings().data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def absolute(relative: str) -> Path:
    path = (data_dir() / relative).resolve()
    if data_dir().resolve() not in path.parents:
        raise ValueError("Chemin de table invalide")
    return path


@dataclass
class Written:
    chemin: str
    nb_lignes: int
    nb_colonnes: int
    schema: list[dict[str, Any]]


def dtype_name(dtype: pl.DataType) -> str:
    """Type simplifié présenté aux auditeurs."""
    if dtype.is_integer():
        return "entier"
    if dtype.is_decimal() or dtype.is_float():
        return "decimal"
    if dtype == pl.Boolean:
        return "booleen"
    if dtype == pl.Date:
        return "date"
    if dtype.is_temporal():
        return "date_heure"
    return "texte"


def schema_of(df: pl.DataFrame) -> list[dict[str, Any]]:
    return [
        {"nom": name, "type": dtype_name(dtype), "dtype": str(dtype)}
        for name, dtype in df.schema.items()
    ]


def write_table(df: pl.DataFrame, engagement_id: uuid.UUID) -> Written:
    """Écrit une table neuve et la rend non modifiable."""
    relative = f"{engagement_id}/{uuid.uuid4()}.parquet"
    path = write_frame(df, relative)
    os.chmod(path, 0o444)
    return Written(relative, df.height, df.width, schema_of(df))


def write_frame(df: pl.DataFrame, relative: str) -> Path:
    """Écriture Parquet déterministe : mêmes données, mêmes octets (NF-04)."""
    path = absolute(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.write_parquet(tmp, compression="zstd", statistics=True)
    tmp.rename(path)
    return path


def write_duckdb_query(
    con: duckdb.DuckDBPyConnection, sql: str, params: list[Any], engagement_id: uuid.UUID
) -> Written:
    """Écrit le résultat d'une requête DuckDB dans une table neuve (gros volumes)."""
    relative = f"{engagement_id}/{uuid.uuid4()}.parquet"
    path = absolute(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # Le chemin est interne (UUID) ; la requête est composée par le moteur, jamais saisie.
    con.execute(f"COPY ({sql}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)", params)  # noqa: S608
    tmp.rename(path)
    os.chmod(path, 0o444)
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
    df_schema = pl.read_parquet_schema(path)
    schema = [{"nom": n, "type": dtype_name(t), "dtype": str(t)} for n, t in df_schema.items()]
    return Written(relative, rows, len(schema), schema)


def is_read_only(relative: str) -> bool:
    """Aucun droit d'écriture sur le fichier (contrôle des droits, quel que soit l'utilisateur)."""
    return not absolute(relative).stat().st_mode & 0o222


@contextmanager
def connect() -> Iterator[duckdb.DuckDBPyConnection]:
    """Connexion DuckDB en mémoire, bornée en mémoire et en threads."""
    s = get_settings()
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"SET memory_limit = '{s.duckdb_memory_limit}'")
        con.execute(f"SET threads = {int(s.duckdb_threads)}")
        yield con
    finally:
        con.close()


def parquet_ref(relative: str) -> str:
    """Référence SQL d'un fichier Parquet (chemin résolu dans le répertoire des données)."""
    path = str(absolute(relative)).replace("'", "''")
    return f"read_parquet('{path}')"


def file_sha256(relative: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with absolute(relative).open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def control_totals(relative: str, schema: list[dict[str, Any]]) -> dict[str, Any]:
    """Totaux de contrôle (DAT-04) : somme exacte et nombre de valeurs de chaque colonne
    numérique, minimum et maximum des dates."""
    numeric = [c["nom"] for c in schema if c["type"] in ("entier", "decimal")]
    dates = [c["nom"] for c in schema if c["type"] in ("date", "date_heure")]
    if not numeric and not dates:
        return {}
    exprs = []
    for name in numeric:
        q = quote_ident(name)
        exprs += [f"sum({q})", f"count({q})"]
    for name in dates:
        q = quote_ident(name)
        exprs += [f"min({q})", f"max({q})"]
    with connect() as con:
        row = con.execute(f"SELECT {', '.join(exprs)} FROM {parquet_ref(relative)}").fetchone()  # noqa: S608
    totals: dict[str, Any] = {}
    values = iter(row)
    for name in numeric:
        total, count = next(values), next(values)
        totals[name] = {"somme": str(total if total is not None else 0), "valeurs": count}
    for name in dates:
        low, high = next(values), next(values)
        totals[name] = {"min": str(low) if low else None, "max": str(high) if high else None}
    return totals


def quote_ident(name: str) -> str:
    """Identifiant SQL entre guillemets (noms de colonnes issus des fichiers importés)."""
    return '"' + name.replace('"', '""') + '"'
