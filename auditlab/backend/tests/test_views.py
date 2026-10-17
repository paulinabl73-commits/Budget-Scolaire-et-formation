import pytest

from app.security.roles import Role
from tests import data_files
from tests.test_datasets import ctx  # noqa: F401
from tests.test_imports import CSV_OPTIONS, run_import, upload


@pytest.fixture
def factures(client, ctx):  # noqa: F811
    up = upload(client, ctx, "factures.csv", data_files.CSV_FR)
    ds = run_import(client, ctx, up, CSV_OPTIONS, "Factures")
    assert ds["statut"] == "pret"
    return ds


def test_dat06_vue_sans_toucher_la_source(client, ctx, factures):  # noqa: F811
    from tests.test_imports import rows

    before = rows(factures["id"])
    body = {
        "nom": "Factures enrichies",
        "champs": [
            {"nom": "TVA", "expression": "[Montant TTC] * 0.18"},
            {"nom": "Catégorie", "expression": "SI(TVA > 1000; 'majeure'; 'mineure')"},
            {"nom": "Mois", "expression": "MOIS(Date)"},
        ],
    }
    resp = client.post(
        f"/api/datasets/{factures['id']}/views", json=body, headers=ctx["da"].headers
    )
    assert resp.status_code == 201, resp.text
    view = resp.json()
    assert view["kind"] == "vue" and view["parent_dataset_id"] == factures["id"]
    assert view["nb_lignes"] == 3 and view["nb_colonnes"] == 8
    assert [c["nom"] for c in view["schema"]][-3:] == ["TVA", "Catégorie", "Mois"]
    assert view["definition"]["valeurs_vides"] == {"TVA": 0, "Catégorie": 0, "Mois": 0}
    # La source est inchangée : même contenu, même empreinte.
    assert rows(factures["id"]).equals(before)
    check = client.get(f"/api/datasets/{factures['id']}/integrity", headers=ctx["aud"].headers)
    assert check.json()["table_intacte"] is True

    # Vue d'une vue, puis modification de la vue (sans données, elle reste modifiable).
    resp = client.post(
        f"/api/datasets/{view['id']}/views",
        json={
            "nom": "Majeures",
            "champs": [{"nom": "Alerte", "expression": "Catégorie = 'majeure'"}],
        },
        headers=ctx["da"].headers,
    )
    assert resp.status_code == 201, resp.text
    resp = client.put(
        f"/api/datasets/{view['id']}/view",
        json={
            "nom": "Factures TVA",
            "champs": [{"nom": "TVA", "expression": "[Montant TTC] * 0.2"}],
        },
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 200 and resp.json()["nom"] == "Factures TVA"
    assert resp.json()["nb_colonnes"] == 6
    resp = client.put(
        f"/api/datasets/{factures['id']}/view",
        json={"champs": [{"nom": "x", "expression": "1"}]},
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 409


def test_dat06_erreurs(client, ctx, factures, account):  # noqa: F811
    url = f"/api/datasets/{factures['id']}"
    bad = client.post(
        f"{url}/views",
        json={"nom": "V", "champs": [{"nom": "x", "expression": "Montant * 2"}]},
        headers=ctx["da"].headers,
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == {"message": "x : Colonne inconnue « Montant »", "position": 0}
    dup = client.post(
        f"{url}/views",
        json={"nom": "V", "champs": [{"nom": "fournisseur", "expression": "1"}]},
        headers=ctx["da"].headers,
    )
    assert dup.status_code == 422 and "déjà utilisé" in dup.json()["detail"]["message"]
    conv = client.post(
        f"{url}/views",
        json={"nom": "V", "champs": [{"nom": "n", "expression": "Fournisseur + 1"}]},
        headers=ctx["da"].headers,
    )
    assert conv.status_code == 422
    # Un auditeur extérieur à la mission ne voit pas la table.
    other = account(Role.AUDITEUR)
    denied = client.post(
        f"{url}/views",
        json={"nom": "V", "champs": [{"nom": "n", "expression": "1"}]},
        headers=other.headers,
    )
    assert denied.status_code == 404


def test_dat06_controle_a_la_saisie(client, ctx, factures):  # noqa: F811
    url = f"/api/datasets/{factures['id']}/expressions/validate"
    ok = client.post(url, json={"expression": "[Montant TTC] > 1000"}, headers=ctx["chef"].headers)
    assert ok.json() == {
        "valide": True,
        "erreur": None,
        "position": None,
        "type": "booleen",
        "apercu": [True, False, False],
        "colonnes": ["Montant TTC"],
    }
    ko = client.post(url, json={"expression": "SI(1"}, headers=ctx["chef"].headers)
    assert ko.json()["valide"] is False and ko.json()["position"] == 4
    ko = client.post(url, json={"expression": "Fournisseur * 2"}, headers=ctx["chef"].headers)
    assert ko.json()["valide"] is False and ko.json()["position"] is None
    fns = client.get("/api/expressions/functions", headers=ctx["chef"].headers).json()
    assert "SI" in fns
