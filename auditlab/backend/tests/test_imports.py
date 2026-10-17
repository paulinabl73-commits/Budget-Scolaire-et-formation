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


def test_dat02_detection_et_apercu(client, ctx):  # noqa: F811
    up = upload(client, ctx, "factures.csv", data_files.CSV_FR)
    resp = client.post(f"/api/uploads/{up['id']}/detect", headers=ctx["aud"].headers)
    assert resp.status_code == 200, resp.text
    det = resp.json()
    opts = det["options"]
    assert (opts["encodage"], opts["separateur"], opts["decimal"], opts["format_date"]) == (
        "cp1252",
        ";",
        ",",
        "%d/%m/%Y",
    )
    types = {c["nom"]: c["type"] for c in opts["colonnes"]}
    assert types == {
        "N° facture": "texte",
        "Fournisseur": "texte",
        "Date": "date",
        "Montant TTC": "decimal",
        "Payée": "booleen",
    }
    apercu = det["apercu"]
    assert apercu["lignes"][0][3] == "1250000.50" and apercu["avertissements"] == {}
    assert len(apercu["lignes_brutes"]) == 3

    # L'utilisateur corrige une option : l'aperçu suit, avec les valeurs non convertibles.
    opts["format_date"] = "%Y-%m-%d"
    resp = client.post(f"/api/uploads/{up['id']}/preview", json=opts, headers=ctx["aud"].headers)
    assert resp.json()["avertissements"] == {"Date": 3}

    # Import avec les options validées dans l'assistant.
    opts["format_date"] = "%d/%m/%Y"
    ds = run_import(client, ctx, up, opts)
    assert ds["statut"] == "pret" and ds["schema"][3]["type"] == "decimal"


def test_dat02_virgule_et_tabulation(client, ctx):  # noqa: F811
    data = b"compte\tsolde\tdate\n401100\t-1500.25\t2026-12-31\n411000\t2300\t2026-12-31\n"
    up = upload(client, ctx, "balance.tsv", data)
    opts = client.post(f"/api/uploads/{up['id']}/detect", headers=ctx["aud"].headers).json()[
        "options"
    ]
    assert opts["separateur"] == "\t" and opts["encodage"] == "utf-8" and opts["decimal"] == "."
    assert [c["type"] for c in opts["colonnes"]] == ["entier", "decimal", "date"]
    up = upload(client, ctx, "f.xlsx", data_files.xlsx())
    det = client.post(f"/api/uploads/{up['id']}/detect", headers=ctx["aud"].headers).json()
    assert det["options"]["feuilles"] == ["Factures"]
    assert det["apercu"]["colonnes"] == [
        {"nom": "Facture", "type": "texte"},
        {"nom": "Montant", "type": "decimal"},
    ]
    up = upload(client, ctx, "x.prn", data_files.fixed_width())
    resp = client.post(f"/api/uploads/{up['id']}/detect", headers=ctx["aud"].headers)
    # Largeur fixe : lignes brutes proposées pour définir les positions des colonnes.
    assert resp.json()["apercu"]["lignes_brutes"][1] == ["A001  Fournitures bureau  0001250"]
    resp = client.post(
        f"/api/uploads/{up['id']}/preview",
        json={"format": "txt_fixe", "colonnes": [{"nom": "code", "debut": 1, "fin": 4}]},
        headers=ctx["aud"].headers,
    )
    assert resp.json()["lignes"] == [["A001"], ["A002"]]


@pytest.mark.parametrize(
    ("values", "kind", "extra"),
    [
        (["12", "1 250", "-3"], "entier", {"milliers": " "}),
        (["1.250.000", "12"], "entier", {"milliers": "."}),
        (["12,50", "3", "(4,00)"], "decimal", {"decimal": ","}),
        (["12.5", "1,250.75"], "decimal", {"decimal": "."}),
        (["31/12/2026", ""], "date", {"format_date": "%d/%m/%Y"}),
        (["20261231", "20260101"], "date", {"format_date": "%Y%m%d"}),
        (["oui", "Non"], "booleen", {}),
        (["A1", "2"], "texte", {}),
        ([None, ""], "texte", {}),
    ],
)
def test_dat02_inference_des_types(values, kind, extra):
    from app.analytics.detect import infer_type

    assert infer_type(values) == (kind, extra)


def test_dat02_encodage_et_separateur():
    from app.analytics.detect import detect_encoding, detect_separator

    assert detect_encoding("Société".encode()) == "utf-8"
    assert detect_encoding("Société générale à Abidjan".encode("cp1252")) in ("cp1252", "latin-1")
    assert detect_separator(["a,b;c", "1,2;3", "4,5;6"]) in (",", ";")
    assert detect_separator(["a|b|c", "1|2|3"]) == "|"
    assert detect_separator(["une seule colonne"]) == ";"
