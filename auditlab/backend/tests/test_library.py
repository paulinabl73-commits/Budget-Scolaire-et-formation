import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.security.roles import Role

RISK = {"libelle": "Fournisseurs fictifs", "cycle": "achats", "categorie": "fraude"}
CONTROL = {
    "libelle": "Validation des créations de fournisseurs",
    "cycle": "achats",
    "type_controle": "preventif",
    "nature": "manuel",
    "frequence": "ponctuel",
}


def test_aud10_bibliotheque(client, account, db):
    chef = account(Role.CHEF_MISSION).headers
    risk = client.post("/api/library/risks", json=RISK, headers=chef)
    assert risk.status_code == 201
    c1 = client.post("/api/library/controls", json=CONTROL, headers=chef).json()
    c2 = client.post(
        "/api/library/controls",
        json={**CONTROL, "libelle": "Rapprochement à trois voies", "nature": "semi_automatique"},
        headers=chef,
    ).json()
    rid = risk.json()["id"]
    resp = client.put(
        f"/api/library/risks/{rid}/controls",
        json={"control_ids": [c1["id"], c2["id"], c1["id"]]},
        headers=chef,
    )
    assert [c["libelle"] for c in resp.json()["controles"]] == [
        "Rapprochement à trois voies",
        "Validation des créations de fournisseurs",
    ]

    resp = client.put(
        f"/api/library/risks/{rid}/controls", json={"control_ids": [c2["id"]]}, headers=chef
    )
    assert len(resp.json()["controles"]) == 1

    resp = client.patch(
        f"/api/library/risks/{rid}", json={"description": "Schéma de fraude"}, headers=chef
    )
    assert resp.json()["description"] == "Schéma de fraude"
    resp = client.patch(
        f"/api/library/controls/{c1['id']}", json={"frequence": "mensuel"}, headers=chef
    )
    assert resp.json()["frequence"] == "mensuel"

    auditeur = account(Role.AUDITEUR).headers
    risks = client.get("/api/library/risks?cycle=achats", headers=auditeur).json()
    assert [r["libelle"] for r in risks] == ["Fournisseurs fictifs"]
    assert client.get("/api/library/risks?cycle=paie", headers=auditeur).json() == []
    assert len(client.get("/api/library/controls?cycle=achats", headers=auditeur).json()) == 2

    assert client.delete(f"/api/library/controls/{c2['id']}", headers=chef).status_code == 204
    assert client.get("/api/library/risks", headers=chef).json()[0]["controles"] == []
    assert client.delete(f"/api/library/risks/{rid}", headers=chef).status_code == 204
    assert client.get("/api/library/risks", headers=chef).json() == []
    actions = db.scalars(select(AuditLog.action).where(AuditLog.object_type == "Risk")).all()
    assert actions == ["create", "update", "delete"]


def test_aud10_controles_de_saisie(client, account):
    chef = account(Role.CHEF_MISSION).headers
    assert (
        client.post(
            "/api/library/risks", json={**RISK, "cycle": "inconnu"}, headers=chef
        ).status_code
        == 422
    )
    rid = client.post("/api/library/risks", json=RISK, headers=chef).json()["id"]
    resp = client.put(
        f"/api/library/risks/{rid}/controls",
        json={"control_ids": [str(uuid.uuid4())]},
        headers=chef,
    )
    assert resp.status_code == 404
    assert (
        client.patch(
            f"/api/library/risks/{uuid.uuid4()}", json={"libelle": "x"}, headers=chef
        ).status_code
        == 404
    )


@pytest.mark.parametrize("role", [Role.AUDITEUR, Role.DATA_ANALYST, Role.ADMIN])
def test_aud10_gestion_reservee(client, account, role):
    h = account(role).headers
    assert client.post("/api/library/risks", json=RISK, headers=h).status_code == 403
    assert client.post("/api/library/controls", json=CONTROL, headers=h).status_code == 403
    assert client.get("/api/library/risks", headers=h).status_code == 200


def test_aud10_audite_sans_acces(client, account):
    assert client.get("/api/library/risks", headers=account(Role.AUDITE).headers).status_code == 403
