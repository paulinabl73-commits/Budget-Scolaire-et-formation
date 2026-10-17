import uuid

from app.security.roles import Role
from tests import helpers
from tests.test_program import CONTROL, RISK


def _library(client, h):
    risk = client.post("/api/library/risks", json=RISK, headers=h).json()
    c = client.post("/api/library/controls", json=CONTROL, headers=h).json()
    client.put(
        f"/api/library/risks/{risk['id']}/controls", json={"control_ids": [c["id"]]}, headers=h
    )
    client.post(
        "/api/library/procedures",
        json={
            "control_id": c["id"],
            "type_test": "efficacite",
            "description": "Revue sur échantillon",
        },
        headers=h,
    )
    return risk


def test_aud09_modele_depuis_la_bibliotheque_et_mission(client, account):
    chef = account(Role.CHEF_MISSION)
    h = chef.headers
    risk = _library(client, h)
    resp = client.post(
        "/api/templates",
        json={
            "nom": "Audit du cycle achats",
            "budget_jours": 25,
            "objectifs": "Évaluer le dispositif de contrôle interne des achats",
            "library_risk_ids": [risk["id"]],
        },
        headers=h,
    )
    assert resp.status_code == 201
    tpl = resp.json()
    assert (tpl["nb_risques"], tpl["nb_controles"], tpl["nb_procedures"]) == (1, 1, 1)
    assert (
        client.post(
            "/api/templates",
            json={"nom": "Audit du cycle achats", "library_risk_ids": [risk["id"]]},
            headers=h,
        ).status_code
        == 409
    )

    m = helpers.mission(client, h, template_id=tpl["id"], budget_jours=None)
    assert m["budget_jours"] == 25
    assert m["objectifs"] == "Évaluer le dispositif de contrôle interne des achats"
    matrix = client.get(f"/api/engagements/{m['id']}/matrix", headers=h).json()
    assert [r["libelle"] for r in matrix["risques"]] == [RISK["libelle"]]
    assert matrix["risques"][0]["source_id"] == risk["id"]
    procs = matrix["risques"][0]["controles"][0]["procedures"]
    assert [(p["reference"], p["description"]) for p in procs] == [
        ("P-01", "Revue sur échantillon")
    ]


def test_aud09_modele_depuis_une_mission(client, account):
    chef = account(Role.CHEF_MISSION)
    h = chef.headers
    m = helpers.mission(client, h, objectifs="Objectifs de la mission source")
    url = f"/api/engagements/{m['id']}"
    r = client.post(f"{url}/risks", json=RISK, headers=h).json()
    c = client.post(f"{url}/controls", json={**CONTROL, "risk_ids": [r["id"]]}, headers=h).json()
    # Un même contrôle couvre deux risques : il reste unique dans le modèle et la copie.
    r2 = client.post(
        f"{url}/risks", json={**RISK, "libelle": "Doubles paiements"}, headers=h
    ).json()
    client.put(f"{url}/risks/{r2['id']}/controls", json={"control_ids": [c["id"]]}, headers=h)
    client.post(
        f"{url}/procedures",
        json={"control_id": c["id"], "type_test": "substantif", "description": "Test de détail"},
        headers=h,
    )

    tpl = client.post(
        "/api/templates", json={"nom": "Modèle achats", "from_engagement_id": m["id"]}, headers=h
    ).json()
    assert (tpl["nb_risques"], tpl["nb_controles"], tpl["nb_procedures"]) == (2, 1, 1)
    assert tpl["objectifs"] == "Objectifs de la mission source" and tpl["budget_jours"] == 30

    new = helpers.mission(client, h, template_id=tpl["id"])
    matrix = client.get(f"/api/engagements/{new['id']}/matrix", headers=h).json()
    assert len(matrix["controles"]) == 1
    assert all(len(rr["controles"]) == 1 for rr in matrix["risques"])
    # Les risques propres à la mission source n'ont pas d'origine bibliothèque.
    assert all(rr["source_id"] is None for rr in matrix["risques"])


def test_aud09_gestion_et_droits(client, account):
    chef = account(Role.CHEF_MISSION)
    risk = _library(client, chef.headers)
    tpl = client.post(
        "/api/templates", json={"nom": "M", "library_risk_ids": [risk["id"]]}, headers=chef.headers
    ).json()
    resp = client.patch(
        f"/api/templates/{tpl['id']}", json={"description": "Version 2026"}, headers=chef.headers
    )
    assert resp.json()["description"] == "Version 2026"
    aud = account(Role.AUDITEUR).headers
    assert client.get("/api/templates", headers=aud).status_code == 200
    assert client.get(f"/api/templates/{tpl['id']}", headers=aud).json()["nom"] == "M"
    assert (
        client.post(
            "/api/templates", json={"nom": "X", "library_risk_ids": [risk["id"]]}, headers=aud
        ).status_code
        == 403
    )
    assert (
        client.post("/api/templates", json={"nom": "Vide"}, headers=chef.headers).status_code == 422
    )
    assert (
        client.post(
            "/api/templates",
            json={"nom": "Y", "library_risk_ids": [str(uuid.uuid4())]},
            headers=chef.headers,
        ).status_code
        == 404
    )
    assert client.delete(f"/api/templates/{tpl['id']}", headers=chef.headers).status_code == 204
    assert client.get("/api/templates", headers=aud).json() == []
    resp = client.post(
        "/api/engagements",
        json={
            "template_id": tpl["id"],
            "titre": "X",
            "date_debut": "2027-01-01",
            "date_fin": "2027-01-31",
            "budget_jours": 3,
        },
        headers=chef.headers,
    )
    assert resp.status_code == 404
