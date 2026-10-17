"""DAT-13 : synthèse."""

from decimal import Decimal

import polars as pl
import pytest

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_dat13_regroupement(client, ctx, db):  # noqa: F811
    df = pl.DataFrame(
        {
            "compte": ["601", "401", "601", "401", "601", None],
            "tiers": ["A", "B", "A", "C", "B", "A"],
            "montant": pl.Series([Decimal(x) for x in ("10.00", "20.00", "30.50", "5.00", "1.00",
                                  "2.00")]).cast(pl.Decimal(18, 2)),
        }
    )  # fmt: skip
    ds = make_dataset(db, ctx["mission"]["id"], df)
    params = {
        "groupes": ["compte"],
        "agregats": [
            {"champ": "montant", "fonction": "somme"},
            {"champ": "montant", "fonction": "moyenne"},
            {"champ": "tiers", "fonction": "distincts"},
            {"champ": "montant", "fonction": "max"},
            {"champ": "montant", "fonction": "ecart_type"},
        ],
    }
    res = analyse(client, ctx, ds, "synthese", params)
    out = result_df(db, res)
    assert out.columns == ["compte", "nombre", "somme_montant", "moyenne_montant",
                           "distincts_tiers", "max_montant", "ecart_type_montant"]  # fmt: skip
    assert out["compte"].to_list() == ["401", "601", None]
    assert out["nombre"].to_list() == [2, 3, 1]
    assert [str(x) for x in out["somme_montant"]] == ["25.00", "41.50", "2.00"]
    assert out["distincts_tiers"].to_list() == [2, 2, 1]
    assert float(out["moyenne_montant"][1]) == pytest.approx(13.8333, abs=1e-4)
    assert res["resultat"] == {"groupes": 3, "lignes": 6}
    res = analyse(client, ctx, ds, "synthese", {"groupes": ["compte", "tiers"]})
    assert result_df(db, res).rows()[0] == ("401", "B", 1)


def test_dat13_agregat_invalide(client, ctx, db):  # noqa: F811
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"a": ["x"], "b": ["y"]}))
    url = f"/api/datasets/{ds.id}/analyses"
    for agg, message in [
        ({"champ": "b", "fonction": "somme"}, "n'est pas numérique"),
        ({"champ": "b", "fonction": "mediane"}, "fonction parmi"),
        ({"champ": "z", "fonction": "nombre"}, "colonne inconnue"),
    ]:
        body = {"operation": "synthese", "parametres": {"groupes": ["a"], "agregats": [agg]}}
        resp = client.post(url, json=body, headers=ctx["da"].headers)
        assert resp.status_code == 422 and message in resp.json()["detail"]
