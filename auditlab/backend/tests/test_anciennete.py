"""DAT-14 : ancienneté (balance âgée)."""

import datetime as dt
from decimal import Decimal

import polars as pl

from tests.analysis_helpers import analyse, result_df
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def test_dat14_balance_agee(client, ctx, db):  # noqa: F811
    ref = dt.date(2026, 12, 31)
    ages = [-5, 0, 30, 31, 60, 61, 400, None]
    df = pl.DataFrame(
        {
            "echeance": [ref - dt.timedelta(days=a) if a is not None else None for a in ages],
            "solde": pl.Series([Decimal(f"{i + 1}00.00") for i in range(8)]).cast(
                pl.Decimal(18, 2)
            ),
        }
    )
    ds = make_dataset(db, ctx["mission"]["id"], df)
    params = {
        "champ_date": "echeance",
        "date_reference": "2026-12-31",
        "tranches": ["30", "60"],
        "champ_montant": "solde",
    }
    res = analyse(client, ctx, ds, "anciennete", params)
    out = result_df(db, res)
    assert out["tranche"].to_list() == [
        "non échu",
        "0 à 30 jours",
        "31 à 60 jours",
        "plus de 60 jours",
    ]
    assert out["nombre"].to_list() == [1, 2, 2, 2]
    assert [str(x) for x in out["total"]] == ["100.00", "500.00", "900.00", "1300.00"]
    assert out["jours_min"].to_list() == [None, 0, 31, 61]
    assert res["resultat"] == {
        "lignes": 7,
        "total_general": "2800.00",
        "sans_date": 1,
        "non_echu": 1,
    }
    # Sans montant : nombres seuls ; tranches par défaut (30, 60, 90, 180, 365 jours).
    res = analyse(client, ctx, ds, "anciennete", {"champ_date": "echeance",
                                                  "date_reference": "2026-12-31"})  # fmt: skip
    out = result_df(db, res)
    assert "total" not in out.columns and out.height == 7
    assert out["nombre"].to_list() == [1, 2, 2, 1, 0, 0, 1]
