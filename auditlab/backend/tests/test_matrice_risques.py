"""REV-14 : matrice des risques par cycle et par assertion, qui alimente le programme."""

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load


def test_rev14_matrice_et_programme(client, rev):  # noqa: F811
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}/risk-matrix"
    chef, aud = rev["chef"].headers, rev["aud"].headers
    empty = client.get(url, headers=aud).json()
    assert len(empty["cycles"]) == 11 and len(empty["assertions"]) == 6
    assert empty["niveaux"] == ["faible", "moyen", "eleve"]
    assert all(c["montant_n"] == "0" and c["significatif"] is None for c in empty["cycles"])
    load(client, rev, f["id"])
    body = {
        "base_seuil": "total_bilan",
        "pct_seuil": "1.5",
        "justification": "Total du bilan retenu",
    }
    client.put(f"/api/audit-files/{f['id']}/materiality", json=body, headers=chef)
    cycles = {c["code"]: c for c in client.get(url, headers=aud).json()["cycles"]}
    assert (
        cycles["tresorerie"]["montant_n"] == "15300000.00" and cycles["tresorerie"]["significatif"]
    )
    assert cycles["personnel"]["montant_n"] == "6400000.00"  # 42 et 66 : racine la plus longue
    assert cycles["provisions"]["montant_n"] == "0" and not cycles["provisions"]["significatif"]
    # Évaluation des cellules (équipe de la mission).
    cells = [
        ("tresorerie", "existence", {"risque_inherent": "eleve", "risque_controle": "moyen"}, "eleve"),
        ("clients", "evaluation", {"risque_inherent": "moyen", "risque_controle": "moyen"}, "moyen"),
        ("stocks", "existence", {"risque_inherent": "faible", "risque_controle": "faible"}, "faible"),
        ("fournisseurs", "exhaustivite", {"risque_inherent": "faible", "risque_controle": "faible",
                                          "risque_important": True}, "eleve"),
        ("immobilisations", "evaluation", {"risque_inherent": "eleve", "risque_controle": "faible",
                                           "commentaire": "Dépréciation du parc"}, "moyen"),
    ]  # fmt: skip
    for cycle, assertion, values, _ in cells:
        resp = client.put(f"{url}/{cycle}/{assertion}", json=values, headers=aud)
        assert resp.status_code == 200, resp.text
    levels = {(c["cycle"], c["assertion"]): c["risque"] for c in resp.json()["cellules"]}
    assert levels == {(c, a): expected for c, a, _, expected in cells}
    assert client.put(f"{url}/inconnu/existence", json={}, headers=aud).status_code == 404
    assert client.put(f"{url}/stocks/existence", json={"risque_inherent": "fort"},
                      headers=aud).status_code == 422  # fmt: skip
    assert (
        client.put(f"{url}/stocks/existence", json={}, headers=rev["da"].headers).status_code == 403
    )
    # Génération du programme de la mission : réservée au chef de mission.
    assert client.post(f"{url}/program", headers=aud).status_code == 403
    result = client.post(f"{url}/program", headers=chef).json()
    assert (result["crees"], result["mis_a_jour"]) == (4, 0)
    assert sum(c["dans_programme"] for c in result["cellules"]) == 4
    matrix = client.get(f"{rev['url']}/matrix", headers=chef).json()
    risks = {r["libelle"]: r for r in matrix["risques"]}
    assert set(risks) == {
        "Trésorerie – Existence : risque élevé",
        "Clients et cotisants – Évaluation : risque moyen",
        "Fournisseurs – Exhaustivité : risque élevé (risque important)",
        "Immobilisations – Évaluation : risque moyen",
    }
    assert risks["Trésorerie – Existence : risque élevé"]["cycle"] == "tresorerie"
    assert (
        risks["Fournisseurs – Exhaustivité : risque élevé (risque important)"]["cycle"] == "achats"
    )
    procedures = {
        r: [p["type_test"] for c in risks[r]["controles"] for p in c["procedures"]] for r in risks
    }
    assert procedures["Trésorerie – Existence : risque élevé"] == ["substantif", "substantif"]
    assert procedures["Clients et cotisants – Évaluation : risque moyen"] == ["substantif"]
    assert sorted(procedures["Fournisseurs – Exhaustivité : risque élevé (risque important)"]) == [
        "efficacite", "substantif", "substantif"]  # fmt: skip
    assert sorted(procedures["Immobilisations – Évaluation : risque moyen"]) == [
        "efficacite",
        "substantif",
    ]
    assert (
        risks["Immobilisations – Évaluation : risque moyen"]["description"]
        == "Dépréciation du parc"
    )
    # Nouvelle génération : pas de doublon, libellés mis à jour.
    client.put(f"{url}/clients/evaluation", json={"risque_inherent": "eleve", "risque_controle": "eleve"},
               headers=aud)  # fmt: skip
    result = client.post(f"{url}/program", headers=chef).json()
    assert (result["crees"], result["mis_a_jour"]) == (0, 4)
    libelles = {
        r["libelle"] for r in client.get(f"{rev['url']}/matrix", headers=chef).json()["risques"]
    }
    assert "Clients et cotisants – Évaluation : risque élevé" in libelles and len(libelles) == 4
