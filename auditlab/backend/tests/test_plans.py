import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.security.roles import Role


@pytest.fixture
def directeur(account):
    return account(Role.DIRECTEUR)


@pytest.fixture
def entites(client, directeur):
    def make(nom):
        return client.post(
            "/api/universe/entities",
            json={"nom": nom, "type": "processus"},
            headers=directeur.headers,
        ).json()

    return {n: make(n) for n in ("Achats", "Paie", "Trésorerie")}


def _item(entity, **kw):
    return {
        "entity_id": entity["id"],
        "budget_jours": 20,
        "periode_debut": "2027-02-01",
        "periode_fin": "2027-03-15",
        **kw,
    }


def _plan(client, headers, annee=2027, **kw):
    resp = client.post("/api/plans", json={"annee": annee, **kw}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_aud04_construction_du_plan(client, directeur, entites, db):
    h = directeur.headers
    plan = _plan(client, h, capacite_jours=220, commentaire="Plan fondé sur la carte des risques")
    assert (plan["version"], plan["statut"], plan["nb_missions"]) == (1, "brouillon", 0)

    url = f"/api/plans/{plan['id']}/items"
    achats = client.post(url, json=_item(entites["Achats"], justification="Score 92"), headers=h)
    assert achats.status_code == 201
    assert achats.json()["titre"] == "Audit Achats"
    paie = client.post(
        url,
        json=_item(
            entites["Paie"],
            titre="Revue de la paie",
            budget_jours=12.5,
            periode_debut="2027-06-01",
            periode_fin="2027-06-30",
        ),
        headers=h,
    )
    assert paie.status_code == 201

    detail = client.get(f"/api/plans/{plan['id']}", headers=h).json()
    assert detail["nb_missions"] == 2 and detail["total_jours"] == 32.5
    assert [i["entity_nom"] for i in detail["items"]] == ["Achats", "Paie"]
    assert detail["capacite_jours"] == 220

    # Une entité ne figure qu'une fois au plan.
    assert client.post(url, json=_item(entites["Achats"]), headers=h).status_code == 409

    item_id = achats.json()["id"]
    resp = client.patch(
        f"{url}/{item_id}", json={"budget_jours": 25, "periode_fin": "2027-04-30"}, headers=h
    )
    assert resp.status_code == 200
    assert resp.json()["budget_jours"] == 25 and resp.json()["periode_fin"] == "2027-04-30"

    assert client.delete(f"{url}/{paie.json()['id']}", headers=h).status_code == 204
    detail = client.get(f"/api/plans/{plan['id']}", headers=h).json()
    assert detail["nb_missions"] == 1 and detail["total_jours"] == 25

    actions = db.scalars(select(AuditLog.action).where(AuditLog.object_type == "PlanItem")).all()
    assert actions == ["create", "create", "update", "delete"]


def test_aud04_controles_de_saisie(client, directeur, entites):
    h = directeur.headers
    plan = _plan(client, h)
    url = f"/api/plans/{plan['id']}/items"
    bad_order = _item(entites["Achats"], periode_debut="2027-05-01", periode_fin="2027-04-01")
    assert client.post(url, json=bad_order, headers=h).status_code == 422
    other_year = _item(entites["Achats"], periode_debut="2026-12-01")
    resp = client.post(url, json=other_year, headers=h)
    assert resp.status_code == 422 and "2027" in resp.json()["detail"]
    assert (
        client.post(url, json=_item(entites["Achats"], budget_jours=0), headers=h).status_code
        == 422
    )
    unknown = {**_item(entites["Achats"]), "entity_id": str(uuid.uuid4())}
    assert client.post(url, json=unknown, headers=h).status_code == 404

    item = client.post(url, json=_item(entites["Achats"]), headers=h).json()
    resp = client.patch(f"{url}/{item['id']}", json={"periode_debut": "2027-05-01"}, headers=h)
    assert resp.status_code == 422
    assert (
        client.patch(f"{url}/{uuid.uuid4()}", json={"budget_jours": 3}, headers=h).status_code
        == 404
    )


def test_aud04_un_seul_plan_par_annee(client, directeur):
    h = directeur.headers
    _plan(client, h, 2027)
    _plan(client, h, 2028)
    assert client.post("/api/plans", json={"annee": 2027}, headers=h).status_code == 409
    plans = client.get("/api/plans", headers=h).json()
    assert [p["annee"] for p in plans] == [2028, 2027]
    assert [p["annee"] for p in client.get("/api/plans?annee=2027", headers=h).json()] == [2027]
    assert client.get(f"/api/plans/{uuid.uuid4()}", headers=h).status_code == 404


def test_aud04_modification_du_plan(client, directeur):
    h = directeur.headers
    plan = _plan(client, h)
    resp = client.patch(
        f"/api/plans/{plan['id']}", json={"capacite_jours": 300, "commentaire": "Révisé"}, headers=h
    )
    assert resp.json()["capacite_jours"] == 300 and resp.json()["commentaire"] == "Révisé"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CHEF_MISSION])
def test_aud04_lecture_seule(client, account, directeur, entites, role):
    plan = _plan(client, directeur.headers)
    h = account(role).headers
    assert client.get(f"/api/plans/{plan['id']}", headers=h).status_code == 200
    assert client.post("/api/plans", json={"annee": 2030}, headers=h).status_code == 403
    assert (
        client.post(
            f"/api/plans/{plan['id']}/items", json=_item(entites["Paie"]), headers=h
        ).status_code
        == 403
    )


@pytest.mark.parametrize("role", [Role.AUDITEUR, Role.DATA_ANALYST, Role.AUDITE])
def test_aud04_acces_refuse(client, account, role):
    assert client.get("/api/plans", headers=account(role).headers).status_code == 403
