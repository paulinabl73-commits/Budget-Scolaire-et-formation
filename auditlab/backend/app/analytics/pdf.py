"""Import de relevés PDF tabulaires (DAT-03), avec pdfplumber.

Deux modes :
- « tableaux » : tableaux détectés par leurs filets, concaténés sur les pages choisies ;
- « colonnes » : le texte de chaque page est restitué en conservant sa mise en page, puis
  découpé selon les positions de colonnes définies par l'utilisateur (comme un fichier à
  largeur fixe) ; les en-têtes répétés en haut de page sont retirés.
"""

from pathlib import Path

import pdfplumber
import polars as pl

from app.analytics.formats import ImportFailure, ReadOptions, _unique_names


def parse_pages(spec: str | None, count: int) -> list[int]:
    """« 1-3,5 » → [0, 1, 2, 4] (indices), bornés au nombre de pages."""
    if not spec:
        return list(range(count))
    pages: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return [p - 1 for p in dict.fromkeys(pages) if 1 <= p <= count]


def layout_lines(path: Path, pages: str | None = None, limit: int | None = None) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for index in parse_pages(pages, len(pdf.pages)):
            text = pdf.pages[index].extract_text(layout=True) or ""
            lines.extend(line.rstrip() for line in text.splitlines() if line.strip())
            if limit and len(lines) >= limit:
                break
    return lines


def read_pdf(path: Path, opts: ReadOptions) -> pl.DataFrame:
    try:
        if opts.mode_pdf == "colonnes":
            return _by_columns(path, opts)
        return _by_tables(path, opts)
    except ImportFailure:
        raise
    except Exception as exc:  # noqa: BLE001 (PDF corrompu, chiffré…)
        raise ImportFailure(f"PDF illisible : {exc}") from exc


def _by_tables(path: Path, opts: ReadOptions) -> pl.DataFrame:
    rows: list[list[str | None]] = []
    header: list[str] | None = None
    with pdfplumber.open(path) as pdf:
        for index in parse_pages(opts.pages, len(pdf.pages)):
            for table in pdf.pages[index].extract_tables():
                cleaned = [[(c or "").replace("\n", " ").strip() or None for c in r] for r in table]
                if opts.entete and cleaned:
                    if header is None:
                        header = [c or "" for c in cleaned[0]]
                    if [c or "" for c in cleaned[0]] == header:
                        cleaned = cleaned[1:]  # en-tête répété sur chaque page
                rows.extend(cleaned)
    if not rows and header is None:
        raise ImportFailure("Aucun tableau détecté : essayez le mode « colonnes »")
    width = max([len(header or [])] + [len(r) for r in rows])
    names = _unique_names((header or []) + [None] * (width - len(header or [])))
    data = [r + [None] * (width - len(r)) for r in rows]
    if opts.limite:
        data = data[: opts.limite]
    return pl.DataFrame(data, schema=dict.fromkeys(names, pl.String), orient="row")


def _by_columns(path: Path, opts: ReadOptions) -> pl.DataFrame:
    specs = [c for c in opts.colonnes if c.debut and c.fin]
    if not specs:
        raise ImportFailure("Définissez les positions de début et de fin de chaque colonne")
    lines = layout_lines(path, opts.pages)[opts.lignes_ignorees :]

    def cut(line: str) -> list[str | None]:
        return [line[c.debut - 1 : c.fin].strip() or None for c in specs]

    rows = [cut(line) for line in lines]
    if opts.entete and rows:
        header = rows[0]
        rows = [r for r in rows[1:] if r != header]
    rows = [r for r in rows if any(r)]
    if opts.limite:
        rows = rows[: opts.limite]
    names = _unique_names(c.nom for c in specs)
    return pl.DataFrame(rows, schema=dict.fromkeys(names, pl.String), orient="row")
