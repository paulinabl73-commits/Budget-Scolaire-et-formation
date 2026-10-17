"""Lot 6 : cadre des analyses et DAT-09 (extraction)."""

import datetime as dt
from decimal import Decimal

import polars as pl
import pytest

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


@pytest.fixture
def factures(db, ctx):  # noqa: F811
    df = pl.DataFrame(
        {
            "piece": ["F1", "F2", "F3", "F4", "F5", "F6"],
            "fournisseur": ["SOGECI", "Bâtir & Co", "SOGECI", None, "Alpha", "Bâtir & Co"],
            "montant": pl.Series(
                [Decimal(x) for x in ("1500.00", "200.50", "980.00", "75.00", "5000.00", "-20.00")]
            ).cast(pl.Decimal(18, 2)),
            "date": [dt.date(2026, 1, d) for d in (5, 6, 7, 31, 15, 20)],
        }
    )
    return make_dataset(db, ctx["mission"]["id"], df, "Factures")


def test_catalogue(client, ctx):  # noqa: F811
    cat = client.get("/api/analyses", headers=ctx["aud"].headers).json()
    ext = next(o for o in cat if o["code"] == "extraction")
    assert ext["exigence"] == "DAT-09" and ext["entrees"] == 1
    assert ext["params"][0]["nom"] == "expression"


def test_dat09_extraction(client, ctx, factures, db):  # noqa: F811
    expr = "montant >= 980 ET fournisseur <> 'Alpha'"
    res = analyse(client, ctx, factures, "extraction", {"expression": expr}, nom="Gros montants")
    assert res["statut"] == "pret", res["erreur"]
    assert res["kind"] == "analyse" and res["operation"] == "extraction"
    assert res["parent_dataset_id"] == str(factures.id)
    assert res["definition"]["entrees"] == [str(factures.id)]
    assert res["resultat"] == {"lignes_source": 6, "lignes_retenues": 2, "pourcentage": 33.33}
    assert res["totaux_controle"]["montant"] == {"somme": "2480.00", "valeurs": 2}
    df = result_df(db, res)
    assert df["piece"].to_list() == ["F1", "F3"]
    assert df.columns == ["piece", "fournisseur", "montant", "date"]
    # Une condition indéterminée (fournisseur vide) n'est pas retenue.
    res = analyse(
        client, ctx, factures, "extraction", {"expression": "NON (fournisseur = 'Alpha')"}
    )
    assert result_df(db, res)["piece"].to_list() == ["F1", "F2", "F3", "F6"]
    res = analyse(client, ctx, factures, "extraction",
                  {"expression": "date > #10/01/2026# ET montant < 0"})  # fmt: skip
    assert result_df(db, res)["piece"].to_list() == ["F6"]


def test_dat09_reproductible(client, ctx, factures):  # noqa: F811
    params = {"expression": "montant > 100"}
    one = analyse(client, ctx, factures, "extraction", params)
    two = analyse(client, ctx, factures, "extraction", params)
    assert one["parquet_sha256"] == two["parquet_sha256"]


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "expression : paramètre obligatoire"),
        ({"expression": "montant * 2"}, "condition (vrai ou faux)"),
        ({"expression": "inconnu > 1"}, "Colonne inconnue « inconnu » (caractère 1)"),
        ({"expression": "montant > 1", "x": 1}, "Paramètre inconnu « x »"),
    ],
)
def test_dat09_parametres_invalides(client, ctx, factures, params, message):  # noqa: F811
    resp = client.post(
        f"/api/datasets/{factures.id}/analyses",
        json={"operation": "extraction", "parametres": params},
        headers=ctx["da"].headers,
    )
    if resp.status_code == 202:  # erreur détectée à l'exécution
        assert message in resp.json()["erreur"]
    else:
        assert resp.status_code == 422 and message in resp.json()["detail"]


def test_analyse_inconnue_et_droits(client, ctx, factures, account):  # noqa: F811
    from app.security.roles import Role

    url = f"/api/datasets/{factures.id}/analyses"
    assert client.post(url, json={"operation": "x"}, headers=ctx["da"].headers).status_code == 404
    other = account(Role.AUDITEUR)
    body = {"operation": "extraction", "parametres": {"expression": "VRAI"}}
    assert client.post(url, json=body, headers=other.headers).status_code == 404
