"""DAT-15 : loi de Benford, sur des jeux de référence conformes et non conformes."""

import math
import random

import polars as pl
import pytest

from app.analytics.operations.benford import conformity, expected, z_stat
from app.analytics.statistics import chi2_sf, normal_sf
from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_lois_attendues_et_statistiques():
    assert sum(expected("premier").values()) == pytest.approx(1)
    assert sum(expected("second").values()) == pytest.approx(1)
    assert sum(expected("deux_premiers").values()) == pytest.approx(1)
    assert expected("premier")[1] == pytest.approx(0.30103, abs=1e-5)
    assert expected("second")[0] == pytest.approx(0.11968, abs=1e-5)
    # Valeurs de référence des tables du khi-deux.
    assert chi2_sf(15.507, 8) == pytest.approx(0.05, abs=1e-4)
    assert chi2_sf(16.919, 9) == pytest.approx(0.05, abs=1e-4)
    assert chi2_sf(2.0, 8) == pytest.approx(0.98101, abs=1e-4)
    assert chi2_sf(150.0, 89) == pytest.approx(5.9e-5, rel=0.05)
    assert chi2_sf(0, 3) == 1.0
    assert normal_sf(1.96) == pytest.approx(0.025, abs=1e-4)
    # Exemple de Nigrini : z avec correction de continuité.
    assert z_stat(0.35, 0.30103, 1000) == pytest.approx(
        (0.04897 - 0.0005) / math.sqrt(0.30103 * 0.69897 / 1000), rel=1e-4
    )
    assert [conformity("premier", m) for m in (0.005, 0.01, 0.014, 0.02)] == [
        "conformite_etroite",
        "conformite_acceptable",
        "conformite_marginale",
        "non_conformite",
    ]


def benford_amounts(n: int, seed: int = 7) -> list[float]:
    rng = random.Random(seed)  # noqa: S311 - données de test
    return [round(10 ** rng.uniform(1, 6), 2) for _ in range(n)]


def test_dat15_population_conforme(client, ctx, db):  # noqa: F811
    df = pl.DataFrame({"montant": benford_amounts(20_000) + [5.0, -0.5]})
    ds = make_dataset(db, ctx["mission"]["id"], df)
    res = analyse(client, ctx, ds, "benford", {"champ": "montant"})
    r = res["resultat"]
    assert r["montants_retenus"] == 20_000  # 5 et -0,5 sous le seuil de 10
    assert r["conformite"] in ("conformite_etroite", "conformite_acceptable")
    assert r["p_valeur"] > 0.01 and r["ddl"] == 8
    assert len(r["chiffres"]) == 9 and r["chiffres"][0]["chiffres"] == 1
    res = analyse(client, ctx, ds, "benford", {"champ": "montant", "test": "deux_premiers"})
    assert res["resultat"]["ddl"] == 89 and len(res["resultat"]["chiffres"]) == 90


def test_dat15_fractionnement_sous_un_seuil(client, ctx, db):  # noqa: F811
    # Fraude type : paiements fractionnés juste sous un seuil d'autorisation de 50 000.
    amounts = benford_amounts(5_000) + [49_500.0 + i for i in range(400)]
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"montant": amounts}))
    res = analyse(client, ctx, ds, "benford", {"champ": "montant", "test": "deux_premiers"})
    r = res["resultat"]
    assert r["conformite"] != "conformite_etroite" and r["p_valeur"] < 0.001
    assert 49 in r["chiffres_significatifs"]
    out = result_df(db, res)
    assert out.columns == ["montant", "chiffres"]
    assert out.filter(pl.col("chiffres") == 49).height >= 400
    assert r["lignes_suspectes"] == out.height
    # Second chiffre : montants négatifs pris en valeur absolue.
    res = analyse(client, ctx, ds, "benford", {"champ": "montant", "test": "second"})
    assert res["resultat"]["ddl"] == 9


def test_dat15_aucune_valeur(client, ctx, db):  # noqa: F811
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"montant": [1.0, 2.0]}))
    res = analyse(client, ctx, ds, "benford", {"champ": "montant"})
    assert res["resultat"]["montants_retenus"] == 0 and res["resultat"]["conformite"] is None
    assert res["nb_lignes"] == 0
