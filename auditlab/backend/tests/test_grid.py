import datetime as dt
import time

import polars as pl
import pytest

from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


@pytest.fixture
def ecritures(db, ctx):  # noqa: F811
    n = 50_000
    df = pl.DataFrame(
        {
            "piece": [f"P{i:06d}" for i in range(n)],
            "compte": [["401100", "411000", "601000", "512000"][i % 4] for i in range(n)],
            "libelle": [f"Facture {'SOGECI' if i % 10 == 0 else 'divers'} n°{i}" for i in range(n)],
            "montant": pl.Series([(i % 1000) * 1.5 for i in range(n)]).cast(pl.Decimal(18, 2)),
            "date": [dt.date(2026, 1, 1) + dt.timedelta(days=i % 365) for i in range(n)],
            "lettrage": [None if i % 3 else "A" for i in range(n)],
        }
    )
    return make_dataset(db, ctx["mission"]["id"], df, "Écritures")


def q(client, ctx, ds, **body):  # noqa: F811
    resp = client.post(f"/api/datasets/{ds.id}/rows", json=body, headers=ctx["aud"].headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_dat07_pagination_et_tri(client, ctx, ecritures):  # noqa: F811
    page = q(client, ctx, ecritures, offset=0, limit=3)
    assert page["total"] == 50_000
    assert page["colonnes"] == ["piece", "compte", "libelle", "montant", "date", "lettrage"]
    assert page["lignes"][0] == [
        "P000000",
        "401100",
        "Facture SOGECI n°0",
        "0.00",
        "2026-01-01",
        "A",
    ]
    page = q(client, ctx, ecritures, offset=10, limit=2, total=False,
             tri=[{"colonne": "montant", "sens": "desc"}, {"colonne": "piece"}])  # fmt: skip
    assert page["total"] is None
    assert [r[3] for r in page["lignes"]] == ["1498.50", "1498.50"]
    assert page["lignes"][0][0] < page["lignes"][1][0]


def test_dat07_filtres_recherche_et_colonnes(client, ctx, ecritures):  # noqa: F811
    f = {
        "compte": {"filterType": "text", "type": "startsWith", "filter": "40"},
        "montant": {"filterType": "number", "type": "inRange", "filter": 100, "filterTo": 200},
    }
    page = q(client, ctx, ecritures, filtres=f, colonnes=["piece", "montant"], limit=1000)
    assert page["colonnes"] == ["piece", "montant"]
    assert all(100 <= float(r[1]) <= 200 for r in page["lignes"])
    assert page["total"] == len(page["lignes"]) == 50 * 17  # (i % 1000) ∈ [68, 132] et i ≡ 0 [4]
    combined = {
        "date": {
            "filterType": "date",
            "operator": "OR",
            "conditions": [
                {"filterType": "date", "type": "lessThan", "dateFrom": "2026-01-03 00:00:00"},
                {"filterType": "date", "type": "equals", "dateFrom": "2026-12-31"},
            ],
        },
        "lettrage": {"filterType": "text", "type": "notBlank"},
    }
    page = q(client, ctx, ecritures, filtres=combined, limit=1000)
    assert {r[4] for r in page["lignes"]} <= {"2026-01-01", "2026-01-02", "2026-12-31"}
    assert all(r[5] == "A" for r in page["lignes"]) and page["total"] > 0
    assert q(client, ctx, ecritures, recherche="sogeci", total=True)["total"] == 5_000
    assert q(client, ctx, ecritures, recherche="SOGECI n°10", limit=5)["lignes"][0][0] == "P000010"
    blank = {"lettrage": {"filterType": "text", "type": "blank"}}
    assert q(client, ctx, ecritures, filtres=blank)["total"] == 50_000 - 16_667
    neq = {"compte": {"filterType": "text", "type": "notEqual", "filter": "401100"}}
    assert q(client, ctx, ecritures, filtres=neq)["total"] == 37_500
    for t, expected in [("notContains", 37_500), ("equals", 12_500), ("endsWith", 12_500),
                        ("contains", 12_500)]:  # fmt: skip
        filt = {"compte": {"filterType": "text", "type": t, "filter": "401100"}}
        assert q(client, ctx, ecritures, filtres=filt)["total"] == expected, t
    gt = {"montant": {"filterType": "number", "type": "greaterThanOrEqual", "filter": "1497"}}
    assert q(client, ctx, ecritures, filtres=gt)["total"] == 100
    nb = {"montant": {"filterType": "number", "type": "blank"}}
    assert q(client, ctx, ecritures, filtres=nb)["total"] == 0


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"colonnes": ["inconnue"]}, "Colonne inconnue"),
        ({"tri": [{"colonne": "x"}]}, "Colonne inconnue"),
        ({"filtres": {"x": {"type": "equals"}}}, "Colonne inconnue"),
        ({"filtres": {"montant": {"filterType": "number", "type": "equals", "filter": "abc"}}},
         "Nombre invalide"),
        ({"filtres": {"date": {"filterType": "date", "type": "equals", "dateFrom": "31/12"}}},
         "Date invalide"),
        ({"filtres": {"piece": {"filterType": "text", "type": "regex", "filter": "a"}}},
         "Filtre texte inconnu"),
        ({"filtres": {"piece": {"filterType": "set", "type": "equals", "filter": "a"}}},
         "Type de filtre inconnu"),
        ({"filtres": {"montant": {"filterType": "number", "type": "like", "filter": 1}}},
         "Filtre inconnu"),
        ({"filtres": {"montant": {"filterType": "number", "type": "equals"}}}, "manquante"),
    ],
)  # fmt: skip
def test_dat07_requetes_invalides(client, ctx, ecritures, body, message):  # noqa: F811
    resp = client.post(f"/api/datasets/{ecritures.id}/rows", json=body, headers=ctx["aud"].headers)
    assert resp.status_code == 422
    assert message in resp.json()["detail"]["message"]


def test_dat07_injection_par_filtre_sans_effet(client, ctx, ecritures):  # noqa: F811
    evil = {"piece": {"filterType": "text", "type": "equals", "filter": "x' OR '1'='1"}}
    assert q(client, ctx, ecritures, filtres=evil)["total"] == 0


def test_dat07_vue_et_volume(client, ctx, db):  # noqa: F811
    n = 1_000_000
    df = pl.DataFrame({"id": pl.int_range(0, n, eager=True), "montant": pl.Series(range(n)) * 0.01})
    ds = make_dataset(db, ctx["mission"]["id"], df, "Gros")
    view = client.post(
        f"/api/datasets/{ds.id}/views",
        json={"nom": "Vue", "champs": [{"nom": "double", "expression": "montant * 2"}]},
        headers=ctx["da"].headers,
    ).json()
    start = time.perf_counter()
    page = client.post(
        f"/api/datasets/{view['id']}/rows",
        json={"offset": 500_000, "limit": 100, "tri": [{"colonne": "double", "sens": "desc"}],
              "filtres": {"id": {"filterType": "number", "type": "greaterThan", "filter": 10}}},
        headers=ctx["aud"].headers,
    ).json()  # fmt: skip
    assert time.perf_counter() - start < 3
    assert page["total"] == n - 11 and len(page["lignes"]) == 100
    assert page["lignes"][0][0] == n - 1 - 500_000
