"""DAT-19 : recherche floue entre fournisseurs et salariés."""

import polars as pl

from app.analytics.operations import floue
from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_dat19_fournisseurs_et_salaries(client, ctx, db):  # noqa: F811
    mid = ctx["mission"]["id"]
    fournisseurs = make_dataset(
        db,
        mid,
        pl.DataFrame(
            {
                "nom": ["ETS KOUASSI JEAN", "SOGECI SARL", "Diallo Awa Services", "Bâtir & Co", ""],
                "iban": ["CI01", "CI02", "CI03", "CI04", "CI05"],
            }
        ),
        "Fournisseurs",
    )
    salaries = make_dataset(
        db,
        mid,
        pl.DataFrame({"nom": ["Kouassi Jean", "DIALLO Awa", "Traoré Moussa"],
                      "matricule": ["M1", "M2", "M3"]}),
        "Salariés",
    )  # fmt: skip
    params = {"champ_gauche": "nom", "champ_droite": "nom"}
    res = analyse(client, ctx, fournisseurs, "floue", params, second=salaries)
    out = result_df(db, res)
    assert out.columns == ["similarite", "nom", "iban", "nom_2", "matricule"]
    assert out.select("iban", "matricule").rows() == [("CI01", "M1"), ("CI03", "M2")]
    assert out["similarite"][0] == 1.0  # « ETS » retiré : noms identiques
    assert res["resultat"] == {"paires": 2, "noms_gauche": 5, "noms_droite": 3}
    res = analyse(client, ctx, fournisseurs, "floue", {**params, "seuil": "1"}, second=salaries)
    assert res["resultat"]["paires"] == 1


def test_dat19_volume_borne(client, ctx, db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(floue, "MAX_PAIRS", 3)
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"nom": ["a", "b"]}))
    res = analyse(client, ctx, ds, "floue", {"champ_gauche": "nom", "champ_droite": "nom"},
                  second=ds)  # fmt: skip
    assert res["statut"] == "erreur" and "50 millions" in res["erreur"]
