"""Jeux de données de référence pour les tests du Module 2."""

import io
import json

import polars as pl

CSV_FR = (
    "N° facture;Fournisseur;Date;Montant TTC;Payée\n"
    "F-001;SOGECI SARL;31/01/2026;1 250 000,50;oui\n"
    "F-002;Bâtir & Co;15/02/2026;300,00;non\n"
    "F-003;SOGECI SARL;28/02/2026;(45,25);oui\n"
).encode("cp1252")


def fixed_width() -> bytes:
    rows = [
        "CODE  LIBELLE             MONTANT",
        "A001  Fournitures bureau  0001250",
        "A002  Carburant           0000300",
    ]
    return ("\n".join(rows) + "\n").encode()


def xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Factures"
    ws.append(["Facture", "Montant"])
    ws.append(["F1", 100.5])
    ws.append(["F2", 200])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def json_nested() -> bytes:
    return json.dumps(
        [
            {"id": 1, "tiers": {"nom": "SOGECI", "pays": "CI"}, "tags": ["a", "b"]},
            {"id": 2, "tiers": {"nom": "BATIR", "pays": "SN"}, "tags": []},
        ]
    ).encode()


def parquet() -> bytes:
    buf = io.BytesIO()
    pl.DataFrame({"compte": ["401100", "411000"], "solde": [-1500.0, 2300.0]}).write_parquet(buf)
    return buf.getvalue()
