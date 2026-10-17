"""DAT-10 : doublons exacts et approchés sur des jeux de référence."""

import time
from decimal import Decimal

import polars as pl
import pytest

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


@pytest.fixture
def paiements(db, ctx):  # noqa: F811
    df = pl.DataFrame(
        {
            "piece": ["P1", "P2", "P3", "P4", "P5", "P6", "P7"],
            "fournisseur": ["SOGECI SARL", "Sogéci  sarl", "Alpha", "SOGECI SARL", "Alpha",
                            "Beta Services", "Beta Service"],
            "montant": pl.Series([Decimal(x) for x in ("100.00", "100.00", "50.00", "100.00",
                                  "50.00", "70.00", "70.00")]).cast(pl.Decimal(18, 2)),
        }
    )  # fmt: skip
    return make_dataset(db, ctx["mission"]["id"], df, "Paiements")


def test_dat10_exacts(client, ctx, paiements, db):  # noqa: F811
    res = analyse(client, ctx, paiements, "doublons", {"cles": ["fournisseur", "montant"]})
    assert res["resultat"] == {"groupes": 2, "lignes_en_double": 4}
    df = result_df(db, res)
    assert df.columns[:2] == ["groupe", "nb_dans_groupe"]
    assert df.select("groupe", "piece").rows() == [(1, "P3"), (1, "P5"), (2, "P1"), (2, "P4")]
    assert df["nb_dans_groupe"].to_list() == [2, 2, 2, 2]


def test_dat10_approches(client, ctx, paiements, db):  # noqa: F811
    res = analyse(
        client, ctx, paiements, "doublons",
        {"cles": ["fournisseur", "montant"], "mode": "approchee", "seuil": "0.95"},
    )  # fmt: skip
    assert res["resultat"]["groupes"] == 3 and res["resultat"]["lignes_en_double"] == 7
    df = result_df(db, res)
    groups = df.group_by("groupe", maintain_order=True).agg(pl.col("piece")).rows()
    assert groups == [(1, ["P1", "P2", "P4"]), (2, ["P3", "P5"]), (3, ["P6", "P7"])]
    assert df.filter(pl.col("piece") == "P6")["similarite"][0] == pytest.approx(0.9846, abs=1e-3)
    # Seuil strict : seuls les identiques après normalisation restent.
    res = analyse(client, ctx, paiements, "doublons",
                  {"cles": ["fournisseur"], "mode": "approchee", "seuil": "1"})  # fmt: skip
    assert res["resultat"]["groupes"] == 2  # SOGECI (3 lignes) et Alpha
    # Champ texte obligatoire en mode approché.
    res = analyse(client, ctx, paiements, "doublons", {"cles": ["montant"], "mode": "approchee"})
    assert res["statut"] == "erreur" and "champ texte" in res["erreur"]


def test_dat10_million_de_lignes_en_moins_de_10_secondes(client, ctx, db):  # noqa: F811
    n = 1_000_000
    df = pl.DataFrame(
        {
            "facture": pl.int_range(0, n, eager=True) % 990_000,
            "montant": (pl.int_range(0, n, eager=True) % 1000).cast(pl.Float64),
        }
    )
    ds = make_dataset(db, ctx["mission"]["id"], df, "Gros")
    start = time.perf_counter()
    res = analyse(client, ctx, ds, "doublons", {"cles": ["facture"]})
    assert time.perf_counter() - start < 10  # NF-10
    assert res["resultat"] == {"groupes": 10_000, "lignes_en_double": 20_000}
