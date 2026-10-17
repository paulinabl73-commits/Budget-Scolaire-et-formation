"""REV-11 : seuil de signification, seuil de planification et seuil d'insignifiance."""

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load


def test_rev11_seuil_de_signification(client, rev):  # noqa: F811
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}/materiality"
    chef, aud = rev["chef"].headers, rev["aud"].headers
    # Sans balance : bases non calculées, montant à saisir.
    state = client.get(url, headers=aud).json()
    assert state["etats_indisponibles"] == "Aucune balance N acceptée"
    assert state["bases"][0] == {"code": "total_bilan", "libelle": "Total du bilan",
                                 "pct_min": "1", "pct_max": "2", "montant": None}  # fmt: skip
    body = {
        "base_seuil": "total_bilan",
        "pct_seuil": "1.5",
        "justification": "Entité à actifs importants",
    }
    resp = client.put(url, json=body, headers=chef)
    assert resp.status_code == 409 and "saisissez le montant" in resp.text
    resp = client.put(url, json={**body, "montant_base": "30000000"}, headers=chef)
    assert resp.status_code == 200 and resp.json()["seuil"]["seuil_signification"] == "450000.00"
    # Balances importées : montants des bases calculés sur les états N.
    load(client, rev, f["id"])
    bases = {b["code"]: b["montant"] for b in client.get(url, headers=aud).json()["bases"]}
    assert bases == {"total_bilan": "31700000.00", "chiffre_affaires": "40000000.00",
                     "resultat": "7100000.00", "capitaux_propres": "20100000.00"}  # fmt: skip
    state = client.put(url, json=body, headers=chef).json()
    s = state["seuil"]
    assert (s["montant_base"], s["seuil_signification"]) == ("31700000.00", "475500.00")
    assert (s["pct_planification"], s["seuil_planification"]) == ("75.0000", "356625.00")
    assert (s["pct_insignifiant"], s["seuil_insignifiant"]) == ("5.0000", "23775.00")
    assert state["avertissements"] == [] and s["justification_seuil"] == body["justification"]
    # Autre base, pourcentages dérivés choisis, hors fourchette : admis et signalé.
    body = {"base_seuil": "resultat", "pct_seuil": "12", "pct_planification": "60",
            "pct_insignifiant": "3", "seuil_variation_pct": "15", "montant_base": "7000000",
            "justification": "Résultat, indicateur suivi par les actionnaires"}  # fmt: skip
    state = client.put(url, json=body, headers=chef).json()
    assert state["seuil"]["seuil_signification"] == "840000.00"
    assert state["seuil"]["seuil_planification"] == "504000.00"
    assert state["seuil"]["seuil_insignifiant"] == "25200.00"
    assert state["seuil"]["seuil_variation_pct"] == "15.0000"
    assert len(state["avertissements"]) == 2
    # Droits et contrôles.
    assert client.put(url, json=body, headers=aud).status_code == 403
    for change in ({"base_seuil": "inconnue"}, {"pct_insignifiant": "70"}, {"justification": "court"},
                   {"pct_seuil": "0"}, {"montant_base": "-5"}):  # fmt: skip
        assert client.put(url, json={**body, **change}, headers=chef).status_code == 422, change
