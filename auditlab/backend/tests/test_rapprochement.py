"""DAT-17 : rapprochement."""

from tests.analysis_helpers import analyse, result_df
from tests.test_datasets import ctx  # noqa: F401
from tests.test_jointure import tables  # noqa: F401


def test_dat17_rapprochement(client, ctx, tables, db):  # noqa: F811
    factures, _, paiements = tables
    params = {
        "cles": [{"gauche": "code", "droite": "facture"}],
        "montant_gauche": "montant",
        "montant_droite": "montant",
        "tolerance": "0.01",
    }
    res = analyse(client, ctx, factures, "rapprochement", params, second=paiements)
    out = result_df(db, res)
    assert out.columns == ["code", "nb_table_1", "montant_table_1", "nb_table_2",
                           "montant_table_2", "ecart", "statut"]  # fmt: skip
    rows = {r[0]: (r[3], str(r[5]), r[6]) for r in out.rows()}
    assert rows == {
        "F1": (1, "0.00", "concordant"),
        "F2": (2, "0.01", "concordant"),  # 250 − (200 + 49,99) dans la tolérance
        "F3": (0, "40.00", "orphelin table 1"),
        "F4": (0, "75.00", "orphelin table 1"),
        "F5": (1, "-10.00", "orphelin table 2"),
    }
    assert res["resultat"] == {
        "concordants": 2,
        "ecarts": 0,
        "orphelines_gauche": 2,
        "orphelines_droite": 1,
        "total_gauche": "465.00",
        "total_droite": "359.99",
        "ecart_total": "105.01",
    }
    res = analyse(client, ctx, factures, "rapprochement", {**params, "tolerance": "0"},
                  second=paiements)  # fmt: skip
    assert res["resultat"]["ecarts"] == 1
