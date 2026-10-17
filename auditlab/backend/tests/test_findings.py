"""CON-01 et CON-02 : fiche constat, criticité et rattachements."""

from tests.finding_helpers import FINDING, create_finding, team  # noqa: F401


def test_con01_fiche_en_cinq_volets(client, team):  # noqa: F811
    f = create_finding(client, team)
    assert f["reference"] == "C-01" and f["statut"] == "brouillon" and f["peut_modifier"]
    for key, value in FINDING.items():
        assert f[key] == value
    assert create_finding(client, team, titre="Deuxième")["reference"] == "C-02"
    resp = client.patch(f"/api/findings/{f['id']}", json={"cause": "Paramétrage par défaut"},
                        headers=team["chef"].headers)  # fmt: skip
    assert resp.status_code == 200 and resp.json()["cause"] == "Paramétrage par défaut"
    # Lecture : Directeur et data analyst ; écriture : auditeurs et chef de la mission.
    assert (
        client.get(f"/api/findings/{f['id']}", headers=team["directeur"].headers).status_code == 200
    )
    assert not client.get(f"/api/findings/{f['id']}", headers=team["da"].headers).json()[
        "peut_modifier"
    ]
    assert client.patch(f"/api/findings/{f['id']}", json={"titre": "x"},
                        headers=team["da"].headers).status_code == 403  # fmt: skip
    assert client.get(f"/api/findings/{f['id']}", headers=team["audite"].headers).status_code == 404
    # Suppression logique d'un brouillon.
    assert client.delete(f"/api/findings/{f['id']}", headers=team["aud"].headers).status_code == 204
    listed = client.get(f"{team['url']}/findings", headers=team["aud"].headers).json()
    assert [x["reference"] for x in listed] == ["C-02"]
    assert create_finding(client, team)["reference"] == "C-03"  # pas de réutilisation


def test_con02_criticite_et_rattachements(client, team):  # noqa: F811
    f = create_finding(
        client, team, criticite="critique", risk_id=team["risk"]["id"],
        control_id=team["control"]["id"], workpaper_ids=[team["wp"]["id"], team["wp"]["id"]],
    )  # fmt: skip
    assert f["criticite"] == "critique"
    assert f["risque"] == "Fournisseurs fictifs" and f["controle"] == "Validation des créations"
    assert f["papiers"] == [
        {"id": team["wp"]["id"], "reference": "A-1", "titre": "Créations de fournisseurs"}
    ]
    create_finding(client, team, titre="Mineur", criticite="faible")
    create_finding(client, team, titre="Moyen")
    listed = client.get(f"{team['url']}/findings", headers=team["chef"].headers).json()
    assert [x["criticite"] for x in listed] == ["critique", "moyenne", "faible"]
    bad = client.post(f"{team['url']}/findings", json={**FINDING, "criticite": "majeure"},
                      headers=team["aud"].headers)  # fmt: skip
    assert bad.status_code == 422
    for key in ("risk_id", "control_id"):
        bad = client.post(f"{team['url']}/findings",
                          json={**FINDING, key: "00000000-0000-0000-0000-000000000000"},
                          headers=team["aud"].headers)  # fmt: skip
        assert bad.status_code == 422
    bad = client.patch(f"/api/findings/{f['id']}", json={"workpaper_ids": ["00000000-0000-0000-0000-000000000000"]},
                       headers=team["aud"].headers)  # fmt: skip
    assert bad.status_code == 422 and "Papier de travail inconnu" in bad.text
