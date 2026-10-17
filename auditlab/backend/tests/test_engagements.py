import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def team(account):
    """Directeur, chef de mission, deux auditeurs et un data analyst."""
    return {
        "dir": account(Role.DIRECTEUR),
        "chef": account(Role.CHEF_MISSION),
        "aud": account(Role.AUDITEUR),
        "aud2": account(Role.AUDITEUR, email="aud2@exemple.org", nom="Second auditeur"),
        "da": account(Role.DATA_ANALYST),
    }


def test_aud06_mission_depuis_le_plan(client, team, db):
    h = team["dir"].headers
    achats = helpers.entity(client, h, "Achats")
    _, items = helpers.validated_plan(client, h, [achats])
    m = helpers.mission(
        client,
        h,
        membres=[(team["chef"].user, "chef_mission"), (team["aud"].user, "auditeur")],
        plan_item_id=items[0]["id"],
        titre=None,
        date_debut=None,
        date_fin=None,
        budget_jours=None,
        objectifs="Évaluer le dispositif de contrôle des achats",
    )
    assert m["reference"] == "M-2027-001"
    assert (m["titre"], m["budget_jours"], m["date_debut"]) == ("Audit Achats", 20, "2027-01-01")
    assert m["entity_nom"] == "Achats" and m["statut"] == "planifiee"
    assert m["chef_nom"] == team["chef"].user.nom
    assert [x["role_mission"] for x in m["membres"]] == ["chef_mission", "auditeur"]

    # Une ligne du plan ne lance qu'une mission.
    again = client.post(
        "/api/engagements",
        json={
            "plan_item_id": items[0]["id"],
            "membres": [{"user_id": str(team["chef"].user.id), "role_mission": "chef_mission"}],
        },
        headers=h,
    )
    assert again.status_code == 409
    log = db.scalar(select(AuditLog).where(AuditLog.object_id == m["id"]))
    assert log.action == "create" and log.apres["reference"] == "M-2027-001"


def test_aud06_plan_non_valide(client, team):
    h = team["dir"].headers
    e = helpers.entity(client, h)
    plan = client.post("/api/plans", json={"annee": 2027}, headers=h).json()
    item = client.post(
        f"/api/plans/{plan['id']}/items",
        json={
            "entity_id": e["id"],
            "budget_jours": 10,
            "periode_debut": "2027-01-01",
            "periode_fin": "2027-01-31",
        },
        headers=h,
    ).json()
    resp = client.post("/api/engagements", json={"plan_item_id": item["id"]}, headers=h)
    assert resp.status_code == 409
    resp = client.post("/api/engagements", json={"plan_item_id": str(uuid.uuid4())}, headers=h)
    assert resp.status_code == 404


def test_aud06_mission_ponctuelle_par_le_chef(client, team):
    chef = team["chef"]
    m = helpers.mission(
        client,
        chef.headers,
        membres=[(team["aud"].user, "auditeur")],
        perimetre="Fournisseurs actifs 2026",
    )
    # Le créateur devient chef de mission.
    assert m["chef_nom"] == chef.user.nom and m["mon_role"] == "chef_mission"
    assert m["plan_id"] is None and m["entity_id"] is None
    second = helpers.mission(client, chef.headers, date_debut="2027-05-01", date_fin="2027-05-31")
    assert second["reference"] == "M-2027-002"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"titre": None}, "titre"),
        ({"date_fin": "2027-01-01"}, "précède"),
        ({"budget_jours": 0}, None),
    ],
)
def test_aud06_controles_de_saisie(client, team, body, message):
    payload = {
        "titre": "X",
        "date_debut": "2027-02-01",
        "date_fin": "2027-03-31",
        "budget_jours": 10,
        **body,
    }
    resp = client.post("/api/engagements", json=payload, headers=team["chef"].headers)
    assert resp.status_code == 422
    if message:
        assert message in str(resp.json()["detail"])


def test_aud06_equipe_valide(client, team):
    h = team["dir"].headers
    chef, aud, da = team["chef"].user, team["aud"].user, team["da"].user
    bad = [
        [(aud, "auditeur")],  # pas de chef (le Directeur ne s'ajoute pas comme chef ici)
        [(chef, "chef_mission"), (aud, "chef_mission")],
        [(chef, "chef_mission"), (da, "auditeur")],
        [(chef, "chef_mission"), (chef, "auditeur")],
    ]
    for membres in bad[1:]:
        body = {
            "titre": "X",
            "date_debut": "2027-02-01",
            "date_fin": "2027-03-31",
            "budget_jours": 10,
            "membres": [{"user_id": str(u.id), "role_mission": r} for u, r in membres],
        }
        assert client.post("/api/engagements", json=body, headers=h).status_code == 422
    # Sans chef désigné, le Directeur créateur devient chef.
    m = helpers.mission(client, h, membres=bad[0])
    assert m["chef_nom"] == team["dir"].user.nom


def test_aud06_visibilite_par_mission(client, team):
    m1 = helpers.mission(client, team["chef"].headers, membres=[(team["aud"].user, "auditeur")])
    m2 = helpers.mission(client, team["chef"].headers, membres=[(team["aud2"].user, "auditeur")])

    def refs(acc):
        return {x["reference"] for x in client.get("/api/engagements", headers=acc.headers).json()}

    assert refs(team["aud"]) == {m1["reference"]}
    assert refs(team["aud2"]) == {m2["reference"]}
    assert refs(team["dir"]) == {m1["reference"], m2["reference"]}
    assert refs(team["da"]) == set()
    assert (
        client.get(f"/api/engagements/{m2['id']}", headers=team["aud"].headers).status_code == 404
    )


def test_aud06_modification_et_equipe(client, team):
    chef = team["chef"]
    m = helpers.mission(client, chef.headers, membres=[(team["aud"].user, "auditeur")])
    url = f"/api/engagements/{m['id']}"
    resp = client.patch(
        url, json={"objectifs": "Nouveaux objectifs", "budget_jours": 35}, headers=chef.headers
    )
    assert resp.json()["objectifs"] == "Nouveaux objectifs" and resp.json()["budget_jours"] == 35
    assert (
        client.patch(url, json={"date_fin": "2026-01-01"}, headers=chef.headers).status_code == 422
    )
    # Un auditeur ne modifie pas la mission.
    assert client.patch(url, json={"titre": "X"}, headers=team["aud"].headers).status_code == 403

    new_team = [
        {"user_id": str(chef.user.id), "role_mission": "chef_mission"},
        {"user_id": str(team["aud2"].user.id), "role_mission": "auditeur"},
        {"user_id": str(team["da"].user.id), "role_mission": "data_analyst"},
    ]
    resp = client.put(f"{url}/members", json=new_team, headers=chef.headers)
    assert sorted(x["nom"] for x in resp.json()["membres"]) == sorted(
        [chef.user.nom, team["aud2"].user.nom, team["da"].user.nom]
    )
    # L'auditeur retiré ne voit plus la mission.
    assert client.get(url, headers=team["aud"].headers).status_code == 404
    assert client.get(url, headers=team["da"].headers).status_code == 200

    staff = client.get("/api/staff", headers=chef.headers).json()
    assert {s["role_mission"] for s in staff} == {
        "chef_mission",
        "superviseur",
        "auditeur",
        "data_analyst",
    }
    cands = client.get(f"{url}/candidates", headers=chef.headers).json()
    assert len(cands) == len(staff)


def test_aud06_droits(client, team, account):
    for role in (Role.AUDITEUR, Role.DATA_ANALYST, Role.ADMIN):
        h = team["aud"].headers if role is Role.AUDITEUR else account(role).headers
        resp = client.post("/api/engagements", json={"titre": "X"}, headers=h)
        assert resp.status_code == 403
    audite = account(Role.AUDITE)
    assert client.get("/api/engagements", headers=audite.headers).json() == []
    admin = account(Role.ADMIN)
    m = helpers.mission(client, team["chef"].headers)
    assert client.get(f"/api/engagements/{m['id']}", headers=admin.headers).status_code == 200
    assert client.get("/api/engagements?statut=planifiee", headers=admin.headers).json()
