"""DAT-16 : jointure."""

from decimal import Decimal

import polars as pl
import pytest

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def dec(*values):
    return pl.Series([Decimal(v) for v in values]).cast(pl.Decimal(18, 2))


@pytest.fixture
def tables(db, ctx):  # noqa: F811
    factures = pl.DataFrame(
        {"code": ["F1", "F2", "F3", "F4"], "fournisseur": ["A", "B", "A", "C"],
         "montant": dec("100.00", "250.00", "40.00", "75.00")}
    )  # fmt: skip
    fournisseurs = pl.DataFrame({"fournisseur": ["A", "B", "D"], "nom": ["Alpha", "Beta", "Delta"]})
    paiements = pl.DataFrame(
        {"facture": ["F1", "F2", "F2", "F5"], "montant": dec("100.00", "200.00", "49.99", "10.00")}
    )
    mid = ctx["mission"]["id"]
    return (
        make_dataset(db, mid, factures, "Factures"),
        make_dataset(db, mid, fournisseurs, "Fournisseurs"),
        make_dataset(db, mid, paiements, "Paiements"),
    )


def test_dat16_jointures(client, ctx, tables, db):  # noqa: F811
    factures, fournisseurs, _ = tables
    cles = [{"gauche": "fournisseur", "droite": "fournisseur"}]
    res = analyse(client, ctx, factures, "jointure", {"cles": cles}, second=fournisseurs)
    out = result_df(db, res)
    assert out.columns == ["code", "fournisseur", "montant", "fournisseur_2", "nom"]
    assert out.select("code", "nom").rows() == [("F1", "Alpha"), ("F2", "Beta"), ("F3", "Alpha")]
    assert res["resultat"] == {"appariees": 3, "orphelines_gauche": 1, "orphelines_droite": 1,
                               "lignes": 3}  # fmt: skip
    res = analyse(client, ctx, factures, "jointure", {"cles": cles, "type": "gauche"},
                  second=fournisseurs)  # fmt: skip
    assert result_df(db, res).select("code", "nom").rows()[-1] == ("F4", None)
    res = analyse(client, ctx, factures, "jointure", {"cles": cles, "type": "non_apparies"},
                  second=fournisseurs)  # fmt: skip
    out = result_df(db, res)
    assert out.select("origine", "code", "nom").rows() == [
        ("table 1", "F4", None),
        ("table 2", None, "Delta"),
    ]


def test_dat16_controles(client, ctx, tables, db):  # noqa: F811
    factures, fournisseurs, _ = tables
    url = f"/api/datasets/{factures.id}/analyses"
    body = {"operation": "jointure", "parametres": {"cles": [{"gauche": "code", "droite": "x"}]}}
    resp = client.post(url, json=body, headers=ctx["da"].headers)
    assert resp.status_code == 422 and "Seconde table attendue" in resp.text
    body["seconde_table_id"] = str(fournisseurs.id)
    resp = client.post(url, json=body, headers=ctx["da"].headers)
    assert resp.status_code == 422 and "colonne inconnue « x »" in resp.text
