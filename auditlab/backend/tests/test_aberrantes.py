"""DAT-18 : valeurs aberrantes."""

import polars as pl
import pytest

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


@pytest.fixture
def notes_de_frais(db, ctx):  # noqa: F811
    values = [100.0 + (i % 11) for i in range(40)] + [900.0, -300.0, None]
    df = pl.DataFrame({"ref": [f"N{i:02d}" for i in range(43)], "montant": values})
    return make_dataset(db, ctx["mission"]["id"], df)


def test_dat18_score_z(client, ctx, notes_de_frais, db):  # noqa: F811
    res = analyse(client, ctx, notes_de_frais, "aberrantes", {"champ": "montant"})
    out = result_df(db, res)
    assert out["ref"].to_list() == ["N40"]  # 900 ; -300 a un |z| < 3
    assert out.columns == ["ref", "montant", "score"]
    assert out["score"][0] > 3
    r = res["resultat"]
    assert r["moyenne"] == pytest.approx(4786 / 42) and r["aberrantes"] == 1
    res = analyse(client, ctx, notes_de_frais, "aberrantes", {"champ": "montant", "seuil": "2"})
    assert result_df(db, res)["ref"].to_list() == ["N40", "N41"]


def test_dat18_ecart_interquartile(client, ctx, notes_de_frais, db):  # noqa: F811
    res = analyse(client, ctx, notes_de_frais, "aberrantes",
                  {"champ": "montant", "methode": "iqr"})  # fmt: skip
    out = result_df(db, res)
    assert out["ref"].to_list() == ["N40", "N41"]
    r = res["resultat"]
    iqr = r["q3"] - r["q1"]
    assert r["borne_haute"] == pytest.approx(r["q3"] + 1.5 * iqr)
    assert out["score"][0] == pytest.approx((900 - r["q3"]) / iqr, abs=1e-3)


def test_dat18_serie_constante(client, ctx, db):  # noqa: F811
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"m": [5.0, 5.0, 5.0]}))
    res = analyse(client, ctx, ds, "aberrantes", {"champ": "m"})
    assert res["resultat"]["aberrantes"] == 0 and res["nb_lignes"] == 0
