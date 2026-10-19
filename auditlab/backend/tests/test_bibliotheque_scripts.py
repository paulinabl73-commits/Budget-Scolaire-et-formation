"""DAT-28 : bibliothèque de tests prêts à l'emploi par cycle, publiée par les data analysts."""

import datetime as dt

import polars as pl
import pytest

from app.scripting import catalog
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


@pytest.fixture
def library(db):
    catalog.seed(db)
    db.commit()


def _frame(colonnes):
    d = dt.date(2026, 3, 6)  # vendredi
    values = {
        "montant": [95_000.0, 95_000.0, 1_200.0, 310.0, 95_000.0],
        "numero_facture": [1, 2, 2, 5, 6],
    }
    out = {}
    for c in colonnes:
        if c.startswith("date"):
            out[c] = [
                d,
                d,
                d + dt.timedelta(days=1),
                d - dt.timedelta(days=3),
                None if c == "date_sortie" else d,
            ]
        else:
            out[c] = values.get(c, ["A", "A", "B", "C", "A"])
    return pl.DataFrame(out)


def test_dat28_tests_livres_executables(client, ctx, db, library):  # noqa: F811
    da = ctx["da"].headers
    cycles = client.get("/api/script-library/cycles", headers=da).json()
    assert set(cycles) == {"achats", "ventes", "paie", "tresorerie", "notes_frais"}
    templates = client.get("/api/script-library", headers=ctx["aud"].headers).json()
    assert len(templates) == 10 and {t["cycle"] for t in templates} == set(cycles)
    for t in templates:
        ds = make_dataset(
            db, ctx["mission"]["id"], _frame(t["colonnes"]), f"Données {t['reference']}"
        )
        s = client.post(f"{ctx['url']}/scripts/from-library", headers=da,
                        json={"modele_id": t["id"], "entrees": [{"type": "table", "id": str(ds.id)}]})  # fmt: skip
        assert s.status_code == 201, s.text
        assert s.json()["modele"] == {"id": t["id"], "version": 1, "reference": t["reference"]}
        run = client.post(f"/api/scripts/{s.json()['id']}/runs", headers=da).json()
        run = client.get(f"/api/script-runs/{run['id']}", headers=da).json()
        assert run["statut"] == "termine", (t["reference"], run["erreur"])
        assert t["indicateur"] in run["indicateurs"] and run["tables"], t["reference"]


def test_dat28_publication_et_versions(client, ctx, account, library):  # noqa: F811
    from app.security.roles import Role

    da, chef = ctx["da"].headers, ctx["chef"].headers
    body = {"reference": "ACH-10", "cycle": "achats", "nom": "Fournisseurs sans numéro fiscal",
            "code": "t = audit.table(audit.tables()[0])\naudit.metric('n', t.height)\n",
            "colonnes": ["fournisseur", "nif"], "indicateur": "n"}  # fmt: skip
    assert client.post("/api/script-library", json=body, headers=chef).status_code == 403
    assert (
        client.post("/api/script-library", json={**body, "cycle": "x"}, headers=da).status_code
        == 422
    )
    assert (
        client.post("/api/script-library", json={**body, "code": "if"}, headers=da).status_code
        == 422
    )
    draft = client.post("/api/script-library", json=body, headers=da).json()
    assert draft["statut"] == "brouillon"
    assert client.post("/api/script-library", json=body, headers=da).status_code == 409
    listed = client.get("/api/script-library?cycle=achats", headers=chef).json()
    assert "ACH-10" not in [t["reference"] for t in listed]  # brouillon invisible
    assert client.post(f"{ctx['url']}/scripts/from-library", json={"modele_id": draft["id"]},
                       headers=da).status_code == 409  # fmt: skip
    v1 = client.post(f"/api/script-library/{draft['id']}/publish", headers=da).json()
    assert v1["statut"] == "publie" and v1["publie_par"]
    assert client.put(f"/api/script-library/{v1['id']}", json=body, headers=da).status_code == 409
    v2 = client.post(f"/api/script-library/{v1['id']}/versions", headers=da).json()
    assert v2["version"] == 2
    assert client.post(f"/api/script-library/{v1['id']}/versions", headers=da).status_code == 409
    edited = client.put(
        f"/api/script-library/{v2['id']}", json={**body, "nom": "Fournisseurs sans NIF"}, headers=da
    )
    assert edited.json()["nom"] == "Fournisseurs sans NIF"
    client.post(f"/api/script-library/{v2['id']}/publish", headers=da)
    every = {(t["reference"], t["version"]): t["statut"]
             for t in client.get("/api/script-library?tous=true", headers=da).json()}  # fmt: skip
    assert every[("ACH-10", 1)] == "remplace" and every[("ACH-10", 2)] == "publie"
    published = [
        t
        for t in client.get("/api/script-library", headers=chef).json()
        if t["reference"] == "ACH-10"
    ]
    assert [t["version"] for t in published] == [2]
    assert (
        client.post(f"/api/script-library/{v2['id']}/retire", headers=da).json()["statut"]
        == "retire"
    )
    assert (
        client.get("/api/script-library", headers=account(Role.AUDITE).headers).status_code == 403
    )
