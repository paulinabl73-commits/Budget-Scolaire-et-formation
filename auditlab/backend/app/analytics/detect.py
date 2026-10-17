"""Assistant d'import (DAT-02) : détection de l'encodage, du séparateur, de l'en-tête et des
types, puis aperçu des 100 premières lignes avec les options retenues."""

import re
from collections import Counter
from pathlib import Path
from typing import Any

from charset_normalizer import from_bytes

from app.analytics.formats import (
    TEXT_FORMATS,
    ReadOptions,
    apply_types,
    read_source,
)
from app.analytics.store import dtype_name

SAMPLE_BYTES = 256 * 1024
PREVIEW_ROWS = 100
SEPARATORS = [";", ",", "\t", "|"]
DATE_FORMATS = [
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "%d/%m/%Y"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{2}-\d{2}-\d{4}$"), "%d-%m-%Y"),
    (re.compile(r"^\d{2}\.\d{2}\.\d{4}$"), "%d.%m.%Y"),
    (re.compile(r"^\d{8}$"), "%Y%m%d"),
]
INTEGER = re.compile(r"^-?\d{1,3}([   .]\d{3})+$|^-?\d+$")
DEC_COMMA = re.compile(r"^-?\(?\d{1,3}([   .]\d{3})*,\d+\)?$|^-?\(?\d+,\d+\)?$")
DEC_DOT = re.compile(r"^-?\(?\d{1,3}([   ,]\d{3})*\.\d+\)?$|^-?\(?\d+\.\d+\)?$")
BOOLEANS = {"oui", "non", "vrai", "faux", "true", "false", "o", "n"}


def detect_encoding(sample: bytes) -> str:
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    best = from_bytes(sample).best()
    if best and best.encoding.replace("_", "-") in ("latin-1", "iso8859-15", "iso-8859-15"):
        return "latin-1"
    return "cp1252"


def detect_separator(lines: list[str]) -> str:
    """Séparateur présent avec le même nombre d'occurrences sur la plupart des lignes."""
    best, best_score = ";", -1.0
    for sep in SEPARATORS:
        counts = [line.count(sep) for line in lines if line.strip()]
        if not counts or max(counts) == 0:
            continue
        mode, freq = Counter(counts).most_common(1)[0]
        score = freq / len(counts) * (1 if mode > 0 else 0) + mode / 1000
        if score > best_score:
            best, best_score = sep, score
    return best


def infer_type(values: list[str]) -> tuple[str, dict[str, str]]:
    """Type le plus précis compatible avec toutes les valeurs non vides."""
    vals = [v.strip() for v in values if v is not None and v.strip() != ""]
    if not vals:
        return "texte", {}
    if all(INTEGER.match(v) for v in vals) and not all(len(v) == 8 and v.isdigit() for v in vals):
        thousands = "." if any(re.search(r"\d\.\d{3}", v) for v in vals) else " "
        return "entier", {"milliers": thousands}
    comma = sum(bool(DEC_COMMA.match(v)) for v in vals)
    dot = sum(bool(DEC_DOT.match(v)) for v in vals)
    ints = sum(bool(INTEGER.match(v)) for v in vals)
    if comma and comma + ints == len(vals):
        return "decimal", {"decimal": ","}
    if dot and dot + ints == len(vals):
        return "decimal", {"decimal": "."}
    for pattern, fmt in DATE_FORMATS:
        if all(pattern.match(v) for v in vals):
            return "date", {"format_date": fmt}
    if {v.lower() for v in vals} <= BOOLEANS:
        return "booleen", {}
    return "texte", {}


def suggest(path: Path, fmt: str) -> dict[str, Any]:
    """Options proposées pour un fichier déposé."""
    opts: dict[str, Any] = {"format": fmt}
    if fmt in ("csv", "txt"):
        sample = path.open("rb").read(SAMPLE_BYTES)
        encoding = detect_encoding(sample)
        text = sample.decode(encoding, errors="replace").lstrip("﻿")
        lines = text.splitlines()[:50]
        if len(sample) == SAMPLE_BYTES and lines:
            lines = lines[:-1]  # dernière ligne possiblement tronquée
        sep = detect_separator(lines)
        opts.update(encodage=encoding, separateur=sep, entete=True)
        raw = read_source(path, ReadOptions.from_dict({**opts, "limite": 1000}))
        colonnes, votes = [], Counter()
        for name in raw.columns:
            kind, extra = infer_type(raw[name].to_list())
            colonnes.append({"nom": name, "type": kind})
            votes.update(extra.items())
        for key in ("decimal", "milliers", "format_date"):
            choices = [(v, n) for (k, v), n in votes.items() if k == key]
            if choices:
                opts[key] = max(choices, key=lambda c: c[1])[0]
        opts["colonnes"] = colonnes
    elif fmt in ("xlsx", "xls"):
        import fastexcel

        reader = fastexcel.read_excel(str(path))
        opts["feuilles"] = reader.sheet_names
        opts["feuille"] = reader.sheet_names[0] if reader.sheet_names else None
    elif fmt == "pdf":
        opts.update(
            mode_pdf="tableaux", entete=True, decimal=",", milliers=" ", format_date="%d/%m/%Y"
        )
    elif fmt == "txt_fixe":
        opts.update(encodage=detect_encoding(path.open("rb").read(SAMPLE_BYTES)), colonnes=[])
    return opts


def preview(path: Path, options: dict[str, Any]) -> dict[str, Any]:
    """Aperçu des 100 premières lignes converties, schéma et avertissements."""
    opts = ReadOptions.from_dict({**options, "limite": PREVIEW_ROWS})
    if (
        opts.format == "pdf"
        and opts.mode_pdf == "colonnes"
        and not any(c.debut and c.fin for c in opts.colonnes)
    ):
        from app.analytics.pdf import layout_lines

        return {
            "colonnes": [],
            "lignes": [],
            "avertissements": {},
            "lignes_brutes": [[line] for line in layout_lines(path, opts.pages, 30)[:30]],
        }
    if opts.format == "txt_fixe" and not any(c.debut and c.fin for c in opts.colonnes):
        # Pas encore de colonnes : lignes brutes pour repérer les positions.
        text = path.open("rb").read(SAMPLE_BYTES).decode(opts.encodage, errors="replace")
        return {
            "colonnes": [],
            "lignes": [],
            "avertissements": {},
            "lignes_brutes": [[line] for line in text.splitlines()[:20]],
        }
    raw = read_source(path, opts)
    types = {c.nom: c.type for c in opts.colonnes if c.type}
    converted = apply_types(raw, types, opts)
    df = converted.df
    if opts.format in TEXT_FORMATS:
        lignes_brutes = raw.head(5).rows()
    else:
        lignes_brutes = []
    return {
        "colonnes": [{"nom": n, "type": dtype_name(t)} for n, t in df.schema.items()],
        "lignes": [[_json(v) for v in row] for row in df.rows()],
        "lignes_brutes": [[_json(v) for v in row] for row in lignes_brutes],
        "avertissements": converted.avertissements,
    }


def _json(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value
    return str(value)
