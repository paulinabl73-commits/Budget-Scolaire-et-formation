"""Lecture des balances, balances auxiliaires et grands livres (REV-05).

Les fichiers viennent des logiciels de la zone (Sage, Odoo, Perfecto, SAARI) ou d'un export
générique, en Excel ou en CSV. Les colonnes sont reconnues par leurs intitulés
(data/logiciels.json) ; l'utilisateur peut imposer une correspondance. Les montants sont lus aux
formats français ou anglais, avec parenthèses ou signe final pour les négatifs.
"""

import csv
import datetime as dt
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import polars as pl

DATA = json.loads((Path(__file__).parent / "data" / "logiciels.json").read_text(encoding="utf-8"))
AMOUNTS = (
    "ouverture_debit", "ouverture_credit", "mouvement_debit", "mouvement_credit",
    "solde_debit", "solde_credit",
)  # fmt: skip
MAX_ROWS = 2_000_000


class ImportError_(ValueError):  # noqa: N801 - distinct de l'ImportError de Python
    pass


def normalize(header: Any) -> str:
    text = unicodedata.normalize("NFKD", str(header or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def parse_amount(value: Any) -> Decimal:
    """« 1 234,56 », « 1.234,56 », « 1,234.56 », « (12) », « 12- » → Decimal."""
    if value is None or value == "":
        return Decimal(0)
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace(" ", "").replace(" ", "")
    text = text.replace("'", "")
    if not text or text in ("-", "—"):
        return Decimal(0)
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("-"):
        negative, text = True, text[:-1]
    if text.startswith("-"):
        negative, text = not negative, text[1:]
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        text = text.replace(thousands, "").replace(decimal_sep, ".")
    elif "," in text:
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ImportError_(f"Montant illisible « {value} »") from exc
    return -number if negative else number


def parse_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.0+)?", text) and 20000 < float(text) < 80000:  # numéro de série Excel
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(float(text)))
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d", "%d/%m/%y",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):  # fmt: skip
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ImportError_(f"Date illisible « {value} »")


def clean_account(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0+", text):  # nombre lu depuis Excel
        text = text.split(".")[0]
    return re.sub(r"[\s.\-]", "", text)


def read_rows(content: bytes, filename: str) -> list[list[Any]]:
    """Toutes les lignes du fichier, en valeurs brutes (première feuille d'un classeur)."""
    suffix = Path(filename).suffix.lower()
    if suffix in (".xlsx", ".xls", ".xlsm"):
        try:
            df = pl.read_excel(io.BytesIO(content), engine="calamine", has_header=False,
                               infer_schema_length=0)  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - classeur illisible
            raise ImportError_("Classeur illisible") from exc
        return [list(r) for r in df.iter_rows()]
    if suffix in (".csv", ".txt"):
        from app.analytics.detect import detect_encoding

        encoding = detect_encoding(content[:200_000])
        text = content.decode(encoding, errors="replace")
        sample = text[:20_000]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
        except csv.Error:
            delimiter = ";"
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    raise ImportError_("Format attendu : Excel (.xlsx, .xls) ou CSV")


@dataclass
class Table:
    columns: dict[str, int]  # champ standard → index de colonne
    rows: list[list[Any]]
    header_row: int
    unknown: list[str] = field(default_factory=list)


def locate(rows: list[list[Any]], kind: str, forced: dict[str, str] | None = None) -> Table:
    """Trouve la ligne d'en-tête (dans les 30 premières) et associe les colonnes aux champs."""
    synonyms = DATA["grand_livre" if kind == "grand_livre" else "balance"]
    forced_norm = {normalize(k): v for k, v in (forced or {}).items()}
    for index, row in enumerate(rows[:30]):
        headers = [normalize(h) for h in row]
        columns: dict[str, int] = {}
        for col, header in enumerate(headers):
            if not header:
                continue
            target = forced_norm.get(header)
            if target is None:
                target = next((f for f, names in synonyms.items() if header in names), None)
            if target and target not in columns:
                columns[target] = col
        if "compte" in columns and len(columns) >= 3:
            unknown = [
                str(row[c]) for c, h in enumerate(headers) if h and c not in columns.values()
            ]
            return Table(columns, rows[index + 1 :], index, unknown)
    raise ImportError_(
        "Ligne d'en-tête introuvable : une colonne « compte » et au moins deux colonnes de "
        "montants sont attendues (précisez la correspondance des colonnes si besoin)"
    )


@dataclass
class BalanceLine:
    compte: str
    libelle: str | None
    amounts: dict[str, Decimal]

    def net(self, prefix: str) -> Decimal:
        return self.amounts[f"{prefix}_debit"] - self.amounts[f"{prefix}_credit"]


def _cell(row: list[Any], cols: dict[str, int], name: str) -> Any:
    index = cols.get(name)
    return row[index] if index is not None and index < len(row) else None


def _split(net: Decimal) -> tuple[Decimal, Decimal]:
    return (net, Decimal(0)) if net >= 0 else (Decimal(0), -net)


def parse_balance(table: Table, digits_only: bool = True) -> list[BalanceLine]:
    cols = table.columns
    has_mvt = "mouvement_debit" in cols and "mouvement_credit" in cols
    has_solde = ("solde_debit" in cols and "solde_credit" in cols) or "solde" in cols
    if not has_mvt and not has_solde:
        raise ImportError_("Colonnes de montants introuvables (mouvements ou soldes)")
    lines: list[BalanceLine] = []
    for row in table.rows[:MAX_ROWS]:

        def get(f: str, row: list[Any] = row) -> Any:
            return _cell(row, cols, f)

        compte = clean_account(get("compte"))
        if not compte or (digits_only and not compte.isdigit()):
            continue  # lignes de total, de titre ou vides
        a = {k: parse_amount(get(k)) for k in AMOUNTS}
        if "ouverture" in cols:
            a["ouverture_debit"], a["ouverture_credit"] = _split(parse_amount(get("ouverture")))
        if "solde" in cols:
            a["solde_debit"], a["solde_credit"] = _split(parse_amount(get("solde")))
        if not has_solde:  # solde = ouverture + mouvements
            net = a["ouverture_debit"] - a["ouverture_credit"]
            net += a["mouvement_debit"] - a["mouvement_credit"]
            a["solde_debit"], a["solde_credit"] = _split(net)
        elif not has_mvt:  # mouvements = solde − ouverture
            net = (a["solde_debit"] - a["solde_credit"]) - (
                a["ouverture_debit"] - a["ouverture_credit"]
            )
            a["mouvement_debit"], a["mouvement_credit"] = _split(net)
        libelle = get("libelle")
        lines.append(BalanceLine(compte, str(libelle).strip()[:300] if libelle else None, a))
    if not lines:
        raise ImportError_("Aucune ligne de compte lue")
    return lines


GL_COLUMNS = ("date", "journal", "piece", "compte", "libelle", "debit", "credit", "utilisateur",
              "date_saisie", "lettrage", "tiers")  # fmt: skip


def parse_ledger(table: Table) -> pl.DataFrame:
    cols = table.columns
    if not {"date", "debit", "credit"} <= set(cols):
        raise ImportError_("Grand livre : colonnes date, compte, débit et crédit attendues")
    data: dict[str, list[Any]] = {c: [] for c in GL_COLUMNS if c in cols}
    for row in table.rows[:MAX_ROWS]:

        def get(f: str, row: list[Any] = row) -> Any:
            return _cell(row, cols, f)

        compte = clean_account(get("compte"))
        if not compte or not compte.isdigit():
            continue
        for c in data:
            value = get(c)
            if c == "compte":
                value = compte
            elif c in ("debit", "credit"):
                value = parse_amount(value)
            elif c in ("date", "date_saisie"):
                value = parse_date(value)
            else:
                value = str(value).strip() if value not in (None, "") else None
            data[c].append(value)
    if not data["compte"]:
        raise ImportError_("Aucune écriture lue")
    schema = {c: (pl.Decimal(20, 2) if c in ("debit", "credit") else pl.Date
                  if c in ("date", "date_saisie") else pl.Utf8) for c in data}  # fmt: skip
    return pl.DataFrame(data, schema=schema)
