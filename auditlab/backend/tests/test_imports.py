import io
from decimal import Decimal

import pytest

from app.analytics.formats import ImportFailure
from app.analytics.sql_source import check_query
from app.security.roles import Role
from tests import data_files
from tests.test_datasets import ctx  # noqa: F401


def upload(client, ctx, name, data, acc="aud"):  # noqa: F811
    resp = client.post(
        f"{ctx['url']}/uploads", files={"file": (name, io.BytesIO(data))}, headers=ctx[acc].headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def run_import(client, ctx, up, options=None, nom="Table", acc="aud"):  # noqa: F811
    body = {"nom": nom, "upload_id": up["id"]}
    if options:
        body["options"] = options
    resp = client.post(f"{ctx['url']}/imports", json=body, headers=ctx[acc].headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


def rows(dataset_id):
    import polars as pl

    from app.analytics.store import absolute
    from app.db import SessionLocal
    from app.models import Dataset

    with SessionLocal() as db:
        ds = db.get(Dataset, dataset_id)
        return pl.read_parquet(absolute(ds.chemin_parquet))


CSV_OPTIONS = {
    "format": "csv",
    "encodage": "cp1252",
    "separateur": ";",
    "decimal": ",",
    "milliers": " ",
    "format_date": "%d/%m/%Y",
    "colonnes": [
        {"nom": "Date", "type": "date"},
        {"nom": "Montant TTC", "type": "decimal"},
        {"nom": "Payée", "type": "booleen"},
    ],
}


def test_dat01_csv_francais(client, ctx):  # noqa: F811
    up = upload(client, ctx, "factures.csv", data_files.CSV_FR)
    assert up["format"] == "csv" and len(up["sha256"]) == 64
    ds = run_import(client, ctx, up, CSV_OPTIONS, "Factures 2026")
    assert ds["statut"] == "pret", ds["erreur"]
    assert ds["nb_lignes"] == 3 and ds["nb_colonnes"] == 5
    assert [c["type"] for c in ds["schema"]] == ["texte", "texte", "date", "decimal", "booleen"]
    df = rows(ds["id"])
    assert df["Fournisseur"][1] == "Bâtir & Co"  # cp1252 → UTF-8
    assert df["Montant TTC"].to_list() == [
        Decimal("1250000.50"),
        Decimal("300.00"),
        Decimal("-45.25"),
    ]
    assert df["Payée"].to_list() == [True, False, True]
    assert str(df["Date"][0]) == "2026-01-31"


def test_dat01_valeurs_non_convertibles_signalees(client, ctx):  # noqa: F811
    data = b"date;montant\n31/01/2026;10\n2026-13-45;abc\n"
    up = upload(client, ctx, "x.csv", data)
    ds = run_import(
        client,
        ctx,
        up,
        {
            "format": "csv",
            "colonnes": [{"nom": "date", "type": "date"}, {"nom": "montant", "type": "decimal"}],
        },
    )
    assert ds["options"]["avertissements"] == {"date": 1, "montant": 1}


def test_dat01_largeur_fixe(client, ctx):  # noqa: F811
    up = upload(client, ctx, "export.prn", data_files.fixed_width())
    assert up["format"] == "txt_fixe"
    ds = run_import(
        client,
        ctx,
        up,
        {
            "format": "txt_fixe",
            "colonnes": [
                {"nom": "code", "debut": 1, "fin": 4},
                {"nom": "libelle", "debut": 7, "fin": 26},
                {"nom": "montant", "debut": 27, "fin": 33, "type": "entier"},
            ],
        },
    )
    df = rows(ds["id"])
    assert df.to_dicts()[0] == {"code": "A001", "libelle": "Fournitures bureau", "montant": 1250}
    bad = run_import(client, ctx, up, {"format": "txt_fixe", "colonnes": [{"nom": "x"}]})
    assert bad["statut"] == "erreur" and "positions" in bad["erreur"]


def test_dat01_excel_json_parquet(client, ctx):  # noqa: F811
    ds = run_import(
        client,
        ctx,
        upload(client, ctx, "f.xlsx", data_files.xlsx()),
        {"format": "xlsx", "feuille": "Factures"},
    )
    assert ds["statut"] == "pret" and rows(ds["id"])["Montant"].to_list() == [100.5, 200.0]
    ds = run_import(client, ctx, upload(client, ctx, "t.json", data_files.json_nested()))
    assert ds["statut"] == "pret"
    assert rows(ds["id"]).columns == ["id", "tiers.nom", "tiers.pays", "tags"]
    assert rows(ds["id"])["tags"].to_list() == ["a, b", ""]
    ds = run_import(client, ctx, upload(client, ctx, "b.parquet", data_files.parquet()))
    assert ds["statut"] == "pret" and ds["nb_lignes"] == 2


def test_dat01_fichier_illisible(client, ctx):  # noqa: F811
    ds = run_import(client, ctx, upload(client, ctx, "faux.xlsx", b"pas un classeur"))
    assert ds["statut"] == "erreur" and "illisible" in ds["erreur"]
    ds = run_import(client, ctx, upload(client, ctx, "faux.json", b"{pas du json"))
    assert ds["statut"] == "erreur"
    ds = run_import(client, ctx, upload(client, ctx, "faux.parquet", b"PAR1"))
    assert ds["statut"] == "erreur"


def test_dat01_controles(client, ctx):  # noqa: F811
    resp = client.post(
        f"{ctx['url']}/uploads",
        files={"file": ("x.exe", io.BytesIO(b"MZ"))},
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 415
    resp = client.post(f"{ctx['url']}/imports", json={"nom": "x"}, headers=ctx["aud"].headers)
    assert resp.status_code == 422
    # Seuls les membres habilités à analyser importent.
    resp = client.post(
        f"{ctx['url']}/uploads",
        files={"file": ("a.csv", io.BytesIO(b"a\n1"))},
        headers=ctx["chef"].headers,
    )
    assert resp.status_code == 201
    up = upload(client, ctx, "a.csv", b"a\n1", acc="da")
    assert run_import(client, ctx, up, acc="da")["statut"] == "pret"


def test_dat01_source_sql(client, ctx, account):  # noqa: F811
    from app.config import get_settings

    admin = account(Role.ADMIN).headers
    url = get_settings().database_url
    resp = client.post("/api/data-sources", json={"nom": "ERP", "url": url}, headers=admin)
    assert resp.status_code == 201 and resp.json()["dialecte"] == "postgresql"
    src = resp.json()
    assert "url" not in src  # l'adresse (et son mot de passe) n'est jamais renvoyée
    assert (
        client.post("/api/data-sources", json={"nom": "ERP", "url": url}, headers=admin).status_code
        == 409
    )
    assert (
        client.post(
            "/api/data-sources", json={"nom": "X", "url": "pas une url"}, headers=admin
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/data-sources", json={"nom": "Y", "url": url}, headers=ctx["aud"].headers
        ).status_code
        == 403
    )
    assert [
        s["nom"] for s in client.get("/api/data-sources", headers=ctx["aud"].headers).json()
    ] == ["ERP"]

    query = "SELECT 'F-001' AS facture, 1250.5 AS montant UNION ALL SELECT 'F-002', 300"
    resp = client.post(
        f"{ctx['url']}/imports",
        json={"nom": "Factures ERP", "source_id": src["id"], "requete": query},
        headers=ctx["aud"].headers,
    )
    ds = resp.json()
    assert ds["statut"] == "pret" and ds["nb_lignes"] == 2 and ds["source_format"] == "sql"
    resp = client.post(
        f"{ctx['url']}/imports",
        json={"nom": "x", "source_id": src["id"], "requete": "DELETE FROM users"},
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM users",
        "SELECT 1; DROP TABLE users",
        "WITH x AS (SELECT 1) DELETE FROM t",
        "UPDATE t SET a = 1",
        "select * from t where 1=1; select 2",
    ],
)
def test_dat01_requete_refusee(query):
    with pytest.raises(ImportFailure):
        check_query(query)


def test_dat01_requete_admise():
    assert check_query("  select 'delete' as mot from t;  ") == "select 'delete' as mot from t"
    assert check_query("WITH a AS (SELECT 1) SELECT * FROM a").startswith("WITH")
