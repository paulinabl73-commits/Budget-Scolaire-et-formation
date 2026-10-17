import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.security.roles import Role

URL = "/api/universe/entities"


@pytest.fixture
def directeur(account):
    return account(Role.DIRECTEUR)


def _create(client, headers, **kw):
    body = {"nom": "Achats", "type": "processus", **kw}
    resp = client.post(URL, json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_aud01_arborescence(client, directeur, db):
    h = directeur.headers
    groupe = _create(client, h, nom="Direction financière", type="direction")
    achats = _create(
        client,
        h,
        nom="Achats",
        parent_id=groupe["id"],
        responsable="M. Koné",
        date_dernier_audit="2024-03-31",
    )
    _create(client, h, nom="ERP Sage", type="systeme", parent_id=achats["id"])

    entities = client.get(URL, headers=h).json()
    assert [e["nom"] for e in entities] == ["Achats", "Direction financière", "ERP Sage"]
    assert achats["parent_id"] == groupe["id"]
    assert achats["date_dernier_audit"] == "2024-03-31"

    entry = db.scalar(select(AuditLog).where(AuditLog.object_id == achats["id"]))
    assert entry.action == "create" and entry.apres["date_dernier_audit"] == "2024-03-31"


def test_aud01_modification_et_deplacement(client, directeur):
    h = directeur.headers
    a = _create(client, h, nom="A", type="direction")
    b = _create(client, h, nom="B", parent_id=a["id"])
    c = _create(client, h, nom="C", parent_id=b["id"])

    # Interdit : rattacher une entité à elle-même ou à un descendant.
    assert (
        client.patch(f"{URL}/{a['id']}", json={"parent_id": c["id"]}, headers=h).status_code == 409
    )
    assert (
        client.patch(f"{URL}/{a['id']}", json={"parent_id": a["id"]}, headers=h).status_code == 409
    )

    resp = client.patch(
        f"{URL}/{c['id']}", json={"parent_id": None, "type": "systeme", "nom": "C2"}, headers=h
    )
    assert resp.json()["parent_id"] is None and resp.json()["type"] == "systeme"
    assert resp.json()["nom"] == "C2"
    assert client.get(f"{URL}/{c['id']}", headers=h).json()["nom"] == "C2"


def test_aud01_parent_inconnu_et_type_invalide(client, directeur):
    h = directeur.headers
    resp = client.post(
        URL, json={"nom": "X", "type": "processus", "parent_id": str(uuid.uuid4())}, headers=h
    )
    assert resp.status_code == 404
    assert client.post(URL, json={"nom": "X", "type": "autre"}, headers=h).status_code == 422
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=h).status_code == 404


def test_aud01_suppression_logique(client, directeur, db):
    h = directeur.headers
    parent = _create(client, h, nom="Parent", type="direction")
    child = _create(client, h, nom="Enfant", parent_id=parent["id"])
    assert client.delete(f"{URL}/{parent['id']}", headers=h).status_code == 409
    assert client.delete(f"{URL}/{child['id']}", headers=h).status_code == 204
    assert client.delete(f"{URL}/{parent['id']}", headers=h).status_code == 204
    assert client.get(URL, headers=h).json() == []
    actions = db.scalars(select(AuditLog.action).where(AuditLog.object_id == child["id"])).all()
    assert actions == ["create", "delete"]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CHEF_MISSION])
def test_aud01_lecture_seule(client, account, directeur, role):
    entity = _create(client, directeur.headers)
    h = account(role).headers
    assert client.get(URL, headers=h).status_code == 200
    assert client.get(f"{URL}/{entity['id']}", headers=h).status_code == 200
    assert client.post(URL, json={"nom": "X", "type": "processus"}, headers=h).status_code == 403
    assert client.patch(f"{URL}/{entity['id']}", json={"nom": "Y"}, headers=h).status_code == 403
    assert client.delete(f"{URL}/{entity['id']}", headers=h).status_code == 403


@pytest.mark.parametrize("role", [Role.AUDITEUR, Role.DATA_ANALYST, Role.AUDITE])
def test_aud01_acces_refuse(client, account, role):
    assert client.get(URL, headers=account(role).headers).status_code == 403
