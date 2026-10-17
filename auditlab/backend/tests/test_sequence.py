"""DAT-11 : ruptures de séquence."""

import polars as pl

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_dat11_numeros_manquants_et_doubles(client, ctx, db):  # noqa: F811
    numbers = [1, 2, 3, 5, 5, 6, 10, 11, 11, 11, 12, None]
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"numero": numbers}))
    res = analyse(client, ctx, ds, "sequence", {"champ": "numero"})
    df = result_df(db, res)
    assert df.rows() == [
        ("manquant", 4, 4, 1),
        ("double", 5, 5, 2),
        ("manquant", 7, 9, 3),
        ("double", 11, 11, 3),
    ]
    assert res["resultat"] == {
        "minimum": 1,
        "maximum": 12,
        "attendus": 12,
        "manquants": 4,
        "plages_manquantes": 2,
        "doubles": 2,
        "valeurs_vides": 1,
    }


def test_dat11_texte_et_pas(client, ctx, db):  # noqa: F811
    pieces = ["CHQ-0100", "CHQ-0110", "CHQ-0140", "CHQ-0145", "sans numéro"]
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"cheque": pieces}))
    res = analyse(client, ctx, ds, "sequence", {"champ": "cheque", "pas": 10})
    assert result_df(db, res).rows() == [("manquant", 120, 130, 2)]
    assert res["resultat"]["manquants"] == 2 and res["resultat"]["valeurs_vides"] == 1
