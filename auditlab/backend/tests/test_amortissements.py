"""RCO-11 : calcul des amortissements (linéaire 30/360, dégressif avec bascule en linéaire)."""

import datetime as dt
from decimal import Decimal as D

from app.cabinet.depreciation import Asset, days360, schedule


def ends(year):
    return dt.date(year, 12, 31)


def test_lineaire_prorata_et_cloture_decalee():
    assert days360(dt.date(2026, 1, 1), dt.date(2026, 12, 31)) == 360
    a = Asset(D(1_200_000), dt.date(2026, 7, 15), 5, "lineaire")
    assert (
        schedule(a, dt.date(2026, 1, 1), dt.date(2026, 12, 31), ends, D(1))["dotation"] == 110_667
    )
    # Exercice clos le 30 juin : premier exercice de 16 jours.
    first = schedule(
        a, dt.date(2025, 7, 1), dt.date(2026, 6, 30), lambda y: dt.date(y, 6, 30), D(1)
    )
    assert first["dotation"] == 0
    full = Asset(D(100), dt.date(2020, 1, 1), 2, "lineaire")
    assert schedule(full, dt.date(2026, 1, 1), dt.date(2026, 12, 31), ends, D("0.01"))["vnc"] == 0


def test_degressif_bascule_en_lineaire():
    a = Asset(D(1_000_000), dt.date(2026, 4, 10), 5, "degressif", D(2))
    dotations = [
        schedule(a, dt.date(y, 1, 1), dt.date(y, 12, 31), ends, D(1))["dotation"]
        for y in range(2026, 2032)
    ]
    assert dotations == [300_000, 280_000, 168_000, 112_000, 112_000, 28_000]
    sold = Asset(
        D(1_000_000), dt.date(2026, 4, 10), 5, "degressif", D(2), cession=dt.date(2027, 3, 15)
    )
    assert (
        schedule(sold, dt.date(2027, 1, 1), dt.date(2027, 12, 31), ends, D(1))["dotation"] == 70_000
    )
