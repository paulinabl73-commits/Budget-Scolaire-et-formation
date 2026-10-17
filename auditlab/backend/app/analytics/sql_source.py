"""Import depuis une base de données déclarée (SQL ou ODBC), en lecture seule (DAT-01)."""

import re

import polars as pl
from sqlalchemy import create_engine, text

from app.analytics.formats import ImportFailure

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|call|exec|execute"
    r"|copy|attach|pragma)\b",
    re.IGNORECASE,
)


def check_query(query: str) -> str:
    """Une seule requête de lecture (SELECT ou WITH), sans instruction de modification."""
    q = query.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", q, re.IGNORECASE):
        raise ImportFailure("Seules les requêtes de lecture (SELECT ou WITH) sont admises")
    if ";" in q:
        raise ImportFailure("Une seule requête à la fois")
    if _FORBIDDEN.search(re.sub(r"'[^']*'", "''", q)):
        raise ImportFailure("La requête contient une instruction de modification")
    return q


def read_query(url: str, query: str, limit: int | None = None) -> pl.DataFrame:
    q = check_query(query)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            # Transaction en lecture seule quand le moteur le permet, annulée en fin de lecture.
            if engine.dialect.name in ("postgresql", "mysql", "mariadb"):
                conn.execute(text("SET TRANSACTION READ ONLY"))
            sql = f"SELECT * FROM ({q}) AS source LIMIT {int(limit)}" if limit else q  # noqa: S608
            df = pl.read_database(text(sql), connection=conn, infer_schema_length=None)
            conn.rollback()
    except ImportFailure:
        raise
    except Exception as exc:  # noqa: BLE001 (erreurs propres à chaque moteur)
        raise ImportFailure(f"Lecture de la source impossible : {exc}") from exc
    finally:
        engine.dispose()
    return df
