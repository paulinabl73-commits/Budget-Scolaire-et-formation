"""API simplifiée des scripts d'analyse (DAT-26), seule interface du script avec la mission.

Le script s'exécute hors de l'application, sans base de données ni réseau : ses tables et
fichiers d'entrée sont déposés dans son répertoire de travail, ses tables produites et ses
indicateurs y sont écrits puis repris par la plateforme. Ce module ne dépend que de polars et
de la bibliothèque standard.

    t = audit.table("Achats 2026")              # table de la mission (DataFrame polars)
    f = audit.import_csv("fournisseurs.csv")    # fichier déposé dans la mission
    d = audit.duplicates(t, ["fournisseur", "montant"])
    audit.save(d, "Doublons achats")            # nouvelle table de la mission
    audit.metric("doublons", d.height)          # indicateur (alerte si seuil dépassé, DAT-29)
"""

import json
import math
import re
from pathlib import Path
from typing import Any

import polars as pl

__all__ = [
    "benford", "duplicates", "files", "gaps", "import_csv", "metric", "save", "table", "tables",
]  # fmt: skip

_WORK = Path(".")
_MANIFEST: dict[str, Any] = {"tables": {}, "fichiers": {}}
_OUTPUTS: list[dict[str, Any]] = []
_METRICS: dict[str, float] = {}
MAX_OUTPUTS = 20


class AuditError(Exception):
    """Erreur d'utilisation de l'API, présentée telle quelle à l'utilisateur."""


def _init(work: Path) -> None:
    """Appelé par le lanceur : répertoire de travail et manifeste des entrées."""
    global _WORK, _MANIFEST
    _WORK = work
    _MANIFEST = json.loads((work / "manifest.json").read_text("utf-8"))


def _flush() -> None:
    out = _WORK / "out"
    out.mkdir(exist_ok=True)
    (out / "result.json").write_text(
        json.dumps({"tables": _OUTPUTS, "indicateurs": _METRICS}, ensure_ascii=False), "utf-8"
    )


def tables() -> list[str]:
    """Noms des tables d'entrée du script."""
    return sorted(_MANIFEST["tables"])


def files() -> list[str]:
    """Noms des fichiers d'entrée du script."""
    return sorted(_MANIFEST["fichiers"])


def table(nom: str) -> pl.DataFrame:
    """Table d'entrée, choisie parmi les entrées du script."""
    entry = _MANIFEST["tables"].get(nom)
    if entry is None:
        raise AuditError(f"Table « {nom} » absente des entrées du script : {', '.join(tables())}")
    return pl.read_parquet(_WORK / entry)


def import_csv(nom: str, separateur: str | None = None, decimale: str = ",") -> pl.DataFrame:
    """Lit un fichier CSV déposé dans la mission (séparateur détecté, virgule décimale par
    défaut : les colonnes numériques au format français sont converties)."""
    entry = _MANIFEST["fichiers"].get(nom)
    if entry is None:
        raise AuditError(f"Fichier « {nom} » absent des entrées du script : {', '.join(files())}")
    raw = (_WORK / entry).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    if separateur is None:
        head = text.split("\n", 1)[0]
        separateur = max((";", ",", "\t", "|"), key=head.count)
    df = pl.read_csv(text.encode(), separator=separateur, infer_schema_length=0)
    number = re.compile(r"^-?[\d  .]*" + re.escape(decimale) + r"?\d*$")
    for col in df.columns:
        values = df[col].drop_nulls()
        if (
            values.len()
            and values.str.contains(r"\d").all()
            and values.map_elements(
                lambda v: bool(number.match(v.strip())), return_dtype=pl.Boolean
            ).all()
        ):
            cleaned = df[col].str.replace_all(r"[  ]", "")
            if decimale == ",":
                cleaned = cleaned.str.replace_all(r"\.", "").str.replace(",", ".")
            df = df.with_columns(cleaned.cast(pl.Float64, strict=False).alias(col))
    return df


def _check_columns(df: pl.DataFrame, colonnes: list[str]) -> None:
    missing = [c for c in colonnes if c not in df.columns]
    if missing:
        raise AuditError(f"Colonnes inconnues : {', '.join(missing)}")


def duplicates(df: pl.DataFrame, colonnes: list[str]) -> pl.DataFrame:
    """Lignes dont les valeurs des colonnes sont identiques à celles d'une autre ligne ;
    colonne « groupe_doublon » (numéro du groupe) et « nb_occurrences »."""
    _check_columns(df, colonnes)
    counted = df.with_columns(pl.len().over(colonnes).alias("nb_occurrences"))
    dup = counted.filter(pl.col("nb_occurrences") > 1).sort(colonnes)
    keys = dup.select(colonnes).unique(maintain_order=True).with_row_index("groupe_doublon", 1)
    return dup.join(keys, on=colonnes, how="left", nulls_equal=True)


def benford(df: pl.DataFrame, colonne: str) -> pl.DataFrame:
    """Premier chiffre significatif des montants non nuls comparé à la loi de Benford :
    effectif, fréquences observée et attendue, écart ; écart absolu moyen (MAD) en dernière
    ligne (chiffre 0)."""
    _check_columns(df, [colonne])
    values = df[colonne].cast(pl.Float64, strict=False).drop_nulls().abs()
    values = values.filter(values > 0)
    digits = values.map_elements(
        lambda v: int(f"{v:e}"[0]), return_dtype=pl.Int64
    ) if values.len() else pl.Series([], dtype=pl.Int64)  # fmt: skip
    total = digits.len()
    rows = []
    for d in range(1, 10):
        n = int((digits == d).sum()) if total else 0
        observed = n / total if total else 0.0
        expected = math.log10(1 + 1 / d)
        rows.append({"chiffre": d, "effectif": n, "observe": observed, "attendu": expected,
                     "ecart": observed - expected})  # fmt: skip
    mad = sum(abs(r["ecart"]) for r in rows) / 9
    rows.append({"chiffre": 0, "effectif": total, "observe": None, "attendu": None, "ecart": mad})
    return pl.DataFrame(rows)


def gaps(df: pl.DataFrame, colonne: str) -> pl.DataFrame:
    """Ruptures d'une séquence numérique : début et fin de chaque intervalle manquant."""
    _check_columns(df, [colonne])
    seq = df[colonne].cast(pl.Int64, strict=False).drop_nulls().unique().sort()
    out = []
    for prev, cur in zip(seq.to_list(), seq.to_list()[1:], strict=False):
        if cur - prev > 1:
            out.append({"debut": prev + 1, "fin": cur - 1, "manquants": cur - prev - 1})
    return pl.DataFrame(out, schema={"debut": pl.Int64, "fin": pl.Int64, "manquants": pl.Int64})


def save(df: pl.DataFrame, nom: str) -> None:
    """Enregistre la table dans la mission à la fin de l'exécution."""
    if not isinstance(df, pl.DataFrame):
        raise AuditError("audit.save attend un DataFrame polars")
    if not nom or len(nom) > 200:
        raise AuditError("Nom de table obligatoire (200 caractères au plus)")
    if len(_OUTPUTS) >= MAX_OUTPUTS:
        raise AuditError(f"Au plus {MAX_OUTPUTS} tables par exécution")
    path = f"out/table_{len(_OUTPUTS)}.parquet"
    (_WORK / "out").mkdir(exist_ok=True)
    df.write_parquet(_WORK / path)
    _OUTPUTS.append({"nom": nom, "fichier": path})
    _flush()


def metric(nom: str, valeur: float) -> None:
    """Indicateur numérique de l'exécution, comparé au seuil d'alerte de la planification."""
    try:
        number = float(valeur)
    except (TypeError, ValueError) as exc:
        raise AuditError(f"Indicateur « {nom} » : valeur numérique attendue") from exc
    if not math.isfinite(number):
        raise AuditError(f"Indicateur « {nom} » : valeur finie attendue")
    _METRICS[str(nom)[:100]] = number
    _flush()
