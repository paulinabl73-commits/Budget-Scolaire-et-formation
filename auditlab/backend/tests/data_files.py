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


PAGE = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents %d 0 R >>")


def pdf_statement() -> bytes:
    """Relevé bancaire de deux pages : tableau quadrillé, en-tête répété sur chaque page."""
    rows = [
        ("Date", "Libelle", "Montant"),
        ("02/01/2026", "Virement SOGECI", "1 250,00"),
        ("05/01/2026", "Frais tenue compte", "-12,50"),
    ]
    page2 = [rows[0], ("10/01/2026", "Remise cheque", "300,00")]

    def page(content_rows):
        ops = ["0.5 w"]
        x_cols, y0, h = [50, 150, 350, 450], 750, 20
        n = len(content_rows)
        for i in range(n + 1):
            ops.append(f"{x_cols[0]} {y0 - i * h} m {x_cols[-1]} {y0 - i * h} l S")
        for x in x_cols:
            ops.append(f"{x} {y0} m {x} {y0 - n * h} l S")
        for i, row in enumerate(content_rows):
            for j, cell in enumerate(row):
                ops.append(f"BT /F1 10 Tf {x_cols[j] + 4} {y0 - (i + 1) * h + 6} Td ({cell}) Tj ET")
        return "\n".join(ops).encode("latin-1")

    contents = [page(rows), page(page2)]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        PAGE % 6,
        PAGE % 7,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ] + [b"<< /Length %d >>\nstream\n" % len(c) + c + b"\nendstream" for c in contents]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
