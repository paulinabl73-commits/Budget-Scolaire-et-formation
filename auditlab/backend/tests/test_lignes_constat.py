"""DAT-31 : des lignes d'anomalie deviennent un constat, avec leurs données en preuve."""

import datetime as dt
from decimal import Decimal

import polars as pl

from tests.analysis_helpers import analyse
from tests.data_helpers import make_dataset
from tests.finding_helpers import team  # noqa: F401


def test_dat31_un_clic(client, team, db):  # noqa: F811
    df = pl.DataFrame(
        {
            "piece": ["P1", "P2", "P3"],
            "fournisseur": ["Alpha", "Alpha", "Beta"],
            "montant": pl.Series([Decimal("100.50"), Decimal("100.50"), Decimal("7.00")]).cast(
                pl.Decimal(18, 2)
            ),
            "date": [dt.date(2026, 3, 1)] * 3,
            "paye": [True, True, False],
        }
    )
    source = make_dataset(db, team["mission"]["id"], df, "Paiements")
    dups = analyse(
        client, {"da": team["da"]}, source, "doublons", {"cles": ["fournisseur", "montant"]}
    )
    # Lignes telles que la grille les reçoit (DAT-07).
    page = client.post(
        f"/api/datasets/{dups['id']}/rows", json={}, headers=team["aud"].headers
    ).json()
    lines = [dict(zip(page["colonnes"], row, strict=True)) for row in page["lignes"]]
    resp = client.post(f"/api/datasets/{dups['id']}/findings",
                       json={"titre": "Paiements en double", "criticite": "elevee", "lignes": lines,
                             "commentaire": "Même fournisseur, même montant"},
                       headers=team["aud"].headers)  # fmt: skip
    assert resp.status_code == 201, resp.text
    finding = resp.json()
    assert finding["reference"] == "C-01" and finding["criticite"] == "elevee"
    assert "2 ligne(s)" in finding["constat"]
    ev = client.get(f"/api/findings/{finding['id']}/evidence", headers=team["aud"].headers).json()
    assert len(ev) == 1 and ev[0]["type"] == "lignes"
    assert ev[0]["empreinte"] == dups["parquet_sha256"]
    assert ev[0]["extrait"]["colonnes"] == page["colonnes"]
    assert [r[2] for r in ev[0]["extrait"]["lignes"]] == ["P1", "P2"]
    # Compléter un constat existant avec une autre ligne.
    one = [dict(zip(page["colonnes"], page["lignes"][0], strict=True))]
    resp = client.post(f"/api/datasets/{dups['id']}/findings",
                       json={"titre": "x", "lignes": one, "finding_id": finding["id"]},
                       headers=team["aud"].headers)  # fmt: skip
    assert resp.status_code == 201 and resp.json()["id"] == finding["id"]
    assert (
        len(
            client.get(
                f"/api/findings/{finding['id']}/evidence", headers=team["aud"].headers
            ).json()
        )
        == 2
    )


def test_dat31_ligne_inventee_refusee(client, team, db):  # noqa: F811
    source = make_dataset(
        db, team["mission"]["id"], pl.DataFrame({"piece": ["P1"], "montant": [10.5]})
    )
    url = f"/api/datasets/{source.id}/findings"
    h = team["aud"].headers
    fake = {"titre": "x", "lignes": [{"piece": "P1", "montant": 99}]}
    resp = client.post(url, json=fake, headers=h)
    assert resp.status_code == 422 and "n'existe pas" in resp.text
    resp = client.post(
        url, json={"titre": "x", "lignes": [{"piece": "P1", "montant": 10.5}]}, headers=h
    )
    assert resp.status_code == 201
    resp = client.post(url, json={"titre": "x", "lignes": [{"inconnue": 1}]}, headers=h)
    assert resp.status_code == 422
    assert client.post(url, json={"titre": "x", "lignes": [{"piece": "P1"}]},
                       headers=team["da"].headers).status_code == 403  # fmt: skip
