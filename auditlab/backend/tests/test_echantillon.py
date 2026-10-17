"""DAT-20 : méthodes d'échantillonnage."""

from decimal import Decimal

import polars as pl
import pytest

from app.analytics.sampling import (
    SamplingError,
    monetary_unit,
    simple_random,
    stratified,
    systematic,
)
from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_selections_pures():
    rows = simple_random(1000, 25, seed=42)
    assert len(set(rows)) == 25 and rows == sorted(rows) and rows == simple_random(1000, 25, 42)
    assert rows != simple_random(1000, 25, 43)
    rows, step, start = systematic(100, 10, seed=1)
    assert (
        step == 10
        and 0 <= start < 10
        and [b - a for a, b in zip(rows, rows[1:], strict=False)] == [10] * 9
    )
    picked = stratified([list(range(0, 90)), list(range(90, 100)), []], 10, seed=3)
    assert [k for k, _ in picked].count(0) == 9 and [k for k, _ in picked].count(1) == 1
    with pytest.raises(SamplingError):
        simple_random(5, 6, 1)
    with pytest.raises(SamplingError):
        systematic(5, 6, 1)
    with pytest.raises(SamplingError):
        stratified([[1]], 2, 1)


def test_mus_selection_par_unite_monetaire():
    amounts = [Decimal(x) for x in ("100", "0", "-50", "5000", "300", "600")]
    sel = monetary_unit(amounts, 4, seed=9)
    assert sel.interval == Decimal("1500.00")  # 6 000 / 4
    # La ligne de 5 000 (> intervalle) est tirée 3 ou 4 fois mais ne figure qu'une fois.
    assert len(sel.hits[3]) >= 3
    assert sum(len(v) for v in sel.hits.values()) == 4
    assert 1 not in sel.hits and 2 not in sel.hits
    with pytest.raises(SamplingError, match="Aucun montant positif"):
        monetary_unit([Decimal(0)], 1, 1)


@pytest.fixture
def factures(db, ctx):  # noqa: F811
    n = 200
    df = pl.DataFrame(
        {
            "facture": [f"F{i:03d}" for i in range(n)],
            "agence": [["Abidjan", "Dakar", "Lomé"][i % 3] for i in range(n)],
            "montant": pl.Series([Decimal(10 * (i + 1)) for i in range(n)]).cast(pl.Decimal(18, 2)),
        }
    )
    return make_dataset(db, ctx["mission"]["id"], df, "Factures")


def test_dat20_quatre_methodes(client, ctx, factures, db):  # noqa: F811
    base = {"taille": 20, "graine": 2026}
    res = analyse(client, ctx, factures, "echantillon", {**base, "methode": "aleatoire"})
    out = result_df(db, res)
    assert out.height == 20 and out.columns[0] == "ligne"
    assert all(f == f"F{n - 1:03d}" for n, f in zip(out["ligne"], out["facture"], strict=True))
    assert res["resultat"]["taille_population"] == 200 and res["resultat"]["graine"] == 2026

    res = analyse(client, ctx, factures, "echantillon", {**base, "methode": "systematique"})
    assert res["resultat"]["intervalle"] == 10 and result_df(db, res).height == 20

    res = analyse(client, ctx, factures, "echantillon",
                  {**base, "methode": "stratifie", "champ_strate": "agence"})  # fmt: skip
    out = result_df(db, res)
    assert out.columns[:2] == ["ligne", "strate"]
    assert [s["echantillon"] for s in res["resultat"]["strates"]] == [7, 7, 6]
    res = analyse(client, ctx, factures, "echantillon",
                  {**base, "methode": "stratifie", "champ_montant": "montant",
                   "bornes": ["500", "1500"]})  # fmt: skip
    assert [s["population"] for s in res["resultat"]["strates"]] == [49, 100, 51]

    res = analyse(client, ctx, factures, "echantillon",
                  {**base, "methode": "mus", "champ_montant": "montant"})  # fmt: skip
    r = res["resultat"]
    assert r["montant_population"] == "201000.00" and r["intervalle"] == "10050.00"
    out = result_df(db, res)
    assert out.columns[:3] == ["ligne", "point_selection", "nb_selections"]
    assert out["nb_selections"].sum() == 20
    # Les grosses factures ont plus de chances d'être tirées.
    assert out["montant"].cast(pl.Float64).mean() > 1005


def test_dat20_erreurs(client, ctx, factures):  # noqa: F811
    res = analyse(client, ctx, factures, "echantillon",
                  {"taille": 500, "graine": 1, "methode": "aleatoire"})  # fmt: skip
    assert res["statut"] == "erreur" and "plus grand que la population" in res["erreur"]
    res = analyse(
        client, ctx, factures, "echantillon", {"taille": 5, "graine": 1, "methode": "mus"}
    )
    assert res["statut"] == "erreur" and "champ montant" in res["erreur"]
    res = analyse(client, ctx, factures, "echantillon",
                  {"taille": 5, "graine": 1, "methode": "stratifie"})  # fmt: skip
    assert res["statut"] == "erreur" and "champ de strate" in res["erreur"]


def test_dat22_graine_enregistree_et_rejouable(client, ctx, factures, db):  # noqa: F811
    mus = {"taille": 15, "methode": "mus", "champ_montant": "montant"}
    first = analyse(client, ctx, factures, "echantillon", mus)
    seed = first["definition"]["parametres"]["graine"]
    assert isinstance(seed, int) and first["resultat"]["graine"] == seed
    # Même graine, mêmes paramètres : même échantillon, octet pour octet.
    again = analyse(client, ctx, factures, "echantillon", {**mus, "graine": seed})
    assert again["parquet_sha256"] == first["parquet_sha256"]
    other = analyse(client, ctx, factures, "echantillon",
                    {"taille": 15, "methode": "aleatoire", "graine": seed + 1})  # fmt: skip
    assert other["parquet_sha256"] != first["parquet_sha256"]
    # La graine figure dans le journal d'audit de la création de la table.
    from sqlalchemy import select

    from app.models import AuditLog

    entry = db.scalar(
        select(AuditLog).where(AuditLog.object_id == first["id"]).order_by(AuditLog.seq)
    )
    assert entry.apres["definition"]["parametres"]["graine"] == seed
