"""Lecture des fichiers sources et conversion des types (DAT-01, DAT-02).

Les fichiers texte (CSV, largeur fixe) sont lus en texte brut puis convertis colonne par
colonne selon les options : séparateur décimal et des milliers à la française, format de date,
types choisis dans l'assistant. Les valeurs non convertibles deviennent vides et sont comptées
(avertissements de l'import), jamais devinées.
"""

import codecs
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

TEXT_FORMATS = {"csv", "txt", "txt_fixe"}
FORMATS_BY_EXTENSION = {
    ".csv": "csv",
    ".txt": "csv",
    ".tsv": "csv",
    ".prn": "txt_fixe",
    ".dat": "txt_fixe",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "xls",
    ".json": "json",
    ".ndjson": "json",
    ".jsonl": "json",
    ".parquet": "parquet",
    ".pdf": "pdf",
}
TYPES = ("texte", "entier", "decimal", "date", "booleen")
SPACES = r"[\s  ]"
TRUE_VALUES = {"1", "oui", "o", "vrai", "true", "t", "yes", "y", "x"}
FALSE_VALUES = {"0", "non", "n", "faux", "false", "f", "no", ""}


class ImportFailure(ValueError):
    """Erreur de lecture présentée telle quelle à l'utilisateur."""


@dataclass
class ColumnSpec:
    nom: str
    type: str | None = None  # None : type d'origine (ou détecté)
    debut: int | None = None  # largeur fixe : position de début (1 = premier caractère)
    fin: int | None = None  # largeur fixe : position de fin incluse


@dataclass
class ReadOptions:
    format: str
    encodage: str = "utf-8"
    separateur: str = ";"
    guillemet: str | None = '"'
    entete: bool = True
    lignes_ignorees: int = 0
    decimal: str = ","
    milliers: str = " "
    format_date: str = "%d/%m/%Y"
    feuille: str | int | None = None
    colonnes: list[ColumnSpec] = field(default_factory=list)
    limite: int | None = None  # lecture partielle (aperçu)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReadOptions":
        values = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        values["colonnes"] = [ColumnSpec(**c) for c in data.get("colonnes", []) or []]
        return cls(**values)


@dataclass
class Conversion:
    df: pl.DataFrame
    avertissements: dict[str, int] = field(default_factory=dict)  # colonne -> valeurs perdues


def to_utf8(path: Path, encoding: str) -> Path:
    """Copie transcodée en UTF-8 (Polars ne lit que l'UTF-8) ; renvoie le chemin à lire."""
    if encoding.lower().replace("_", "-") in ("utf-8", "utf8", "ascii"):
        return path
    target = Path(tempfile.mkstemp(suffix=".csv")[1])
    with open(path, "rb") as src, open(target, "w", encoding="utf-8") as dst:
        reader = codecs.getreader(encoding)(src, errors="replace")
        shutil.copyfileobj(reader, dst, 1024 * 1024)
    return target


def _unique_names(names: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for i, raw in enumerate(names):
        name = (str(raw).strip().lstrip("\ufeff") if raw is not None else "") or f"colonne_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        result.append(name)
    return result


def read_delimited(path: Path, opts: ReadOptions) -> pl.DataFrame:
    source = to_utf8(path, opts.encodage)
    try:
        df = pl.read_csv(
            source,
            separator=opts.separateur,
            has_header=opts.entete,
            skip_rows=opts.lignes_ignorees,
            infer_schema=False,
            quote_char=opts.guillemet,
            n_rows=opts.limite,
            truncate_ragged_lines=True,
            missing_utf8_is_empty_string=False,
            encoding="utf8-lossy",
        )
    except pl.exceptions.ComputeError as exc:
        raise ImportFailure(f"Lecture impossible : {exc}") from exc
    finally:
        if source != path:
            source.unlink(missing_ok=True)
    return df.rename(dict(zip(df.columns, _unique_names(df.columns), strict=True)))


def read_fixed_width(path: Path, opts: ReadOptions) -> pl.DataFrame:
    """TXT à largeur fixe : colonnes définies par l'utilisateur (positions 1 à n incluses)."""
    specs = [c for c in opts.colonnes if c.debut and c.fin]
    if not specs:
        raise ImportFailure("Définissez les positions de début et de fin de chaque colonne")
    source = to_utf8(path, opts.encodage)
    try:
        lines = pl.read_csv(
            source,
            separator="\x1f",
            has_header=False,
            infer_schema=False,
            quote_char=None,
            new_columns=["ligne"],
            skip_rows=opts.lignes_ignorees + (1 if opts.entete else 0),
            n_rows=opts.limite,
            encoding="utf8-lossy",
            truncate_ragged_lines=True,
        )
    finally:
        if source != path:
            source.unlink(missing_ok=True)
    names = _unique_names(c.nom for c in specs)
    return lines.select(
        pl.col("ligne").str.slice(c.debut - 1, c.fin - c.debut + 1).str.strip_chars().alias(n)
        for c, n in zip(specs, names, strict=True)
    )


def read_excel(path: Path, opts: ReadOptions) -> pl.DataFrame:
    sheet: dict[str, Any] = {"sheet_id": 1}
    if isinstance(opts.feuille, str) and opts.feuille:
        sheet = {"sheet_name": opts.feuille}
    elif isinstance(opts.feuille, int):
        sheet = {"sheet_id": opts.feuille}
    try:
        df = pl.read_excel(
            path,
            engine="calamine",
            has_header=opts.entete,
            read_options={"skip_rows": opts.lignes_ignorees, "n_rows": opts.limite},
            **sheet,
        )
    except Exception as exc:  # noqa: BLE001 (erreurs du moteur Excel, variées)
        raise ImportFailure(f"Classeur illisible : {exc}") from exc
    return df.rename(dict(zip(df.columns, _unique_names(df.columns), strict=True)))


def _flatten(df: pl.DataFrame) -> pl.DataFrame:
    """Aplatit les objets imbriqués (a.b) ; les listes restent en texte JSON."""
    while any(isinstance(t, pl.Struct) for t in df.dtypes):
        cols = []
        for name, dtype in df.schema.items():
            if isinstance(dtype, pl.Struct):
                cols.extend(
                    pl.col(name).struct.field(f.name).alias(f"{name}.{f.name}")
                    for f in dtype.fields
                )
            else:
                cols.append(pl.col(name))
        df = df.select(cols)
    lists = [n for n, t in df.schema.items() if isinstance(t, pl.List | pl.Array)]
    if lists:
        df = df.with_columns(pl.col(n).cast(pl.List(pl.String)).list.join(", ") for n in lists)
    return df


def read_json(path: Path, opts: ReadOptions) -> pl.DataFrame:
    try:
        df = pl.read_json(path)
    except Exception:  # noqa: BLE001 (format JSON non tabulaire : essai en NDJSON)
        try:
            df = pl.read_ndjson(path)
        except Exception as exc:  # noqa: BLE001
            raise ImportFailure("JSON attendu : tableau d'objets ou un objet par ligne") from exc
    df = _flatten(df)
    return df.head(opts.limite) if opts.limite else df


def read_parquet(path: Path, opts: ReadOptions) -> pl.DataFrame:
    try:
        return pl.read_parquet(path, n_rows=opts.limite)
    except Exception as exc:  # noqa: BLE001
        raise ImportFailure(f"Fichier Parquet illisible : {exc}") from exc


READERS = {
    "csv": read_delimited,
    "txt": read_delimited,
    "txt_fixe": read_fixed_width,
    "xlsx": read_excel,
    "xls": read_excel,
    "json": read_json,
    "parquet": read_parquet,
}


def read_source(path: Path, opts: ReadOptions) -> pl.DataFrame:
    if opts.format == "pdf":
        from app.analytics.pdf import read_pdf

        return read_pdf(path, opts)
    reader = READERS.get(opts.format)
    if reader is None:
        raise ImportFailure(f"Format non pris en charge : {opts.format}")
    return reader(path, opts)


# --- Conversion des types ---------------------------------------------------------------


def _clean_number(col: pl.Expr, opts: ReadOptions) -> pl.Expr:
    expr = col.cast(pl.String).str.strip_chars()
    if opts.milliers:
        expr = expr.str.replace_all(
            SPACES if opts.milliers.isspace() else re.escape(opts.milliers), ""
        )
    expr = expr.str.replace_all(SPACES, "")
    if opts.decimal != ".":
        expr = expr.str.replace(opts.decimal, ".", literal=True)
    # Montants négatifs entre parenthèses (usage comptable) : (1 250,00) -> -1250.00
    return (
        pl.when(expr.str.contains(r"^\(.*\)$"))
        .then(pl.lit("-") + expr.str.strip_chars("()"))
        .otherwise(expr)
    )


def decimal_scale(values: pl.Series, opts: ReadOptions) -> int:
    """Nombre de décimales observées (6 au plus) pour un type décimal exact."""
    cleaned = pl.DataFrame({"v": values}).select(_clean_number(pl.col("v"), opts).alias("v"))["v"]
    lengths = cleaned.drop_nulls().str.extract(r"\.(\d+)$").str.len_chars().drop_nulls()
    return min(int(lengths.max() or 0), 6) if len(lengths) else 0


def convert_column(df: pl.DataFrame, name: str, kind: str, opts: ReadOptions) -> pl.Series:
    col = pl.col(name)
    if kind == "texte":
        expr = col.cast(pl.String)
    elif kind == "entier":
        expr = _clean_number(col, opts).cast(pl.Int64, strict=False)
    elif kind == "decimal":
        if df.schema[name].is_numeric():
            expr = col.cast(pl.Float64)
        else:
            expr = _clean_number(col, opts).cast(
                pl.Decimal(38, decimal_scale(df[name], opts)), strict=False
            )
    elif kind == "date":
        dtype = df.schema[name]
        if dtype == pl.Date:
            expr = col
        elif dtype.is_temporal():
            expr = col.cast(pl.Date)
        else:
            expr = (
                col.cast(pl.String)
                .str.strip_chars()
                .str.strptime(pl.Date, opts.format_date, strict=False)
            )
    elif kind == "booleen":
        low = col.cast(pl.String).str.strip_chars().str.to_lowercase()
        expr = (
            pl.when(low.is_in(list(TRUE_VALUES)))
            .then(True)
            .when(low.is_in(list(FALSE_VALUES)))
            .then(False)
            .otherwise(None)
        )
    else:
        raise ImportFailure(f"Type inconnu : {kind}")
    return df.select(expr.alias(name)).to_series()


def apply_types(df: pl.DataFrame, types: dict[str, str], opts: ReadOptions) -> Conversion:
    """Convertit les colonnes demandées et compte les valeurs non convertibles."""
    warnings: dict[str, int] = {}
    columns = []
    for name in df.columns:
        kind = types.get(name)
        if not kind:
            columns.append(df[name])
            continue
        converted = convert_column(df, name, kind, opts)
        original = df[name].cast(pl.String).str.strip_chars()
        lost = int(((original.is_not_null()) & (original != "") & converted.is_null()).sum())
        if lost:
            warnings[name] = lost
        columns.append(converted)
    return Conversion(pl.DataFrame(columns), warnings)
