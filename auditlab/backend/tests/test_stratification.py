"""DAT-12 : stratification."""

from decimal import Decimal

import polars as pl

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_dat12_tranches(client, ctx, db):  # noqa: F811
    amounts = ["-50.00", "0.00", "999.99", "1000.00", "4500.50", "12000.00", None]
    df = pl.DataFrame(
        {"montant": pl.Series([Decimal(a) if a else None for a in amounts]).cast(pl.Decimal(18, 2))}
    )
    ds = make_dataset(db, ctx["mission"]["id"], df)
    res = analyse(
        client, ctx, ds, "stratification", {"champ": "montant", "bornes": ["0", "1000", "5000"]}
    )
    out = result_df(db, res)
    assert out["tranche"].to_list() == [
        "moins de 0",
        "de 0 à moins de 1000",
        "de 1000 à moins de 5000",
        "5000 et plus",
    ]
    assert out["nombre"].to_list() == [1, 2, 2, 1]
    assert [str(x) for x in out["total"]] == ["-50.00", "999.99", "5500.50", "12000.00"]
    assert out["part_nombre"].to_list() == [16.67, 33.33, 33.33, 16.67]
    assert res["resultat"] == {"lignes": 6, "total_general": "18450.49", "valeurs_vides": 1}
    assert out["borne_inf"][0] is None and str(out["borne_sup"][0]) == "0.000000"


def test_dat12_bornes_invalides(client, ctx, db):  # noqa: F811
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"m": [1.5], "t": ["a"]}))
    url = f"/api/datasets/{ds.id}/analyses"
    for params, message in [
        ({"champ": "m", "bornes": ["10", "5"]}, "croissantes"),
        ({"champ": "m", "bornes": ["a"]}, "nombre attendu"),
        ({"champ": "t", "bornes": ["1"]}, "type attendu"),
        ({"champ": "m", "bornes": "1"}, "liste de 1 à 50"),
    ]:
        resp = client.post(
            url,
            json={"operation": "stratification", "parametres": params},
            headers=ctx["da"].headers,
        )
        assert resp.status_code == 422 and message in resp.json()["detail"], params
    res = analyse(client, ctx, ds, "stratification", {"champ": "m", "bornes": ["1,5"]})
    assert result_df(db, res)["nombre"].to_list() == [0, 1]
