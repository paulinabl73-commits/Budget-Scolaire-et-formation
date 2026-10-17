import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.security.roles import Role

NEW_USER = {
    "email": "nouvel.auditeur@exemple.org",
    "nom": "Nouvel Auditeur",
    "role": "auditeur",
    "password": "MotDePasse-Solide-2026",
}

NON_ADMIN = [r for r in Role if r is not Role.ADMIN]


@pytest.mark.parametrize("role", NON_ADMIN)
def test_gestion_des_utilisateurs_refusee_hors_administrateur(client, account, make_user, role):
    acc = account(role)
    target = make_user(Role.DATA_ANALYST, email="cible@exemple.org")
    h = acc.headers
    calls = [
        client.get("/api/users", headers=h),
        client.post("/api/users", json=NEW_USER, headers=h),
        client.get(f"/api/users/{target.id}", headers=h),
        client.patch(f"/api/users/{target.id}", json={"nom": "x"}, headers=h),
        client.delete(f"/api/users/{target.id}", headers=h),
        client.post(f"/api/users/{target.id}/unlock", headers=h),
        client.post(f"/api/users/{target.id}/reset-mfa", headers=h),
        client.post("/api/teams", json={"nom": "x"}, headers=h),
    ]
    assert [c.status_code for c in calls] == [403] * len(calls)


def test_routes_refusees_sans_authentification(client):
    for method, url in [
        ("get", "/api/users"),
        ("post", "/api/users"),
        ("get", "/api/teams"),
        ("get", "/api/audit-log"),
        ("get", "/api/roles"),
    ]:
        assert getattr(client, method)(url).status_code == 401


def test_cycle_de_vie_utilisateur(client, account, db):
    admin = account(Role.ADMIN)
    h = admin.headers
    team = client.post("/api/teams", json={"nom": "Achats"}, headers=h).json()

    created = client.post("/api/users", json={**NEW_USER, "team_ids": [team["id"]]}, headers=h)
    assert created.status_code == 201
    uid = created.json()["id"]
    assert created.json()["teams"][0]["nom"] == "Achats"
    assert client.post("/api/users", json=NEW_USER, headers=h).status_code == 409

    resp = client.patch(
        f"/api/users/{uid}", json={"role": "chef_mission", "nom": "Chef"}, headers=h
    )
    assert resp.json()["role"] == "chef_mission"
    resp = client.patch(f"/api/users/{uid}", json={"actif": False, "team_ids": []}, headers=h)
    assert resp.json()["actif"] is False and resp.json()["teams"] == []
    assert client.get(f"/api/users/{uid}", headers=h).status_code == 200

    assert client.delete(f"/api/users/{uid}", headers=h).status_code == 204
    assert client.get(f"/api/users/{uid}", headers=h).status_code == 404
    assert uid not in [u["id"] for u in client.get("/api/users", headers=h).json()]

    entries = db.scalars(
        select(AuditLog).where(AuditLog.object_id == uid).order_by(AuditLog.seq)
    ).all()
    assert [e.action for e in entries] == ["create", "update", "update", "delete"]
    assert entries[1].avant == {"nom": "Nouvel Auditeur", "role": "auditeur"}
    assert all(e.user_id == admin.user.id for e in entries)


def test_validation_creation(client, account):
    h = account(Role.ADMIN).headers
    weak = client.post("/api/users", json={**NEW_USER, "password": "faible"}, headers=h)
    assert weak.status_code == 422 and "12 caractères" in weak.json()["detail"]
    bad_role = client.post("/api/users", json={**NEW_USER, "role": "pirate"}, headers=h)
    assert bad_role.status_code == 422
    import uuid

    bad_team = client.post(
        "/api/users", json={**NEW_USER, "team_ids": [str(uuid.uuid4())]}, headers=h
    )
    assert bad_team.status_code == 422
    assert client.get(f"/api/users/{uuid.uuid4()}", headers=h).status_code == 404


def test_administrateur_ne_peut_se_retirer_ses_droits(client, account):
    admin = account(Role.ADMIN)
    url = f"/api/users/{admin.user.id}"
    assert client.patch(url, json={"role": "auditeur"}, headers=admin.headers).status_code == 409
    assert client.patch(url, json={"actif": False}, headers=admin.headers).status_code == 409
    assert client.delete(url, headers=admin.headers).status_code == 409
    assert client.patch(url, json={"nom": "Admin"}, headers=admin.headers).status_code == 200


def test_changement_de_role_ferme_les_sessions(client, account, make_user):
    from tests.conftest import login

    admin = account(Role.ADMIN)
    user = make_user(Role.AUDITEUR)
    headers = login(client, user)
    client.patch(f"/api/users/{user.id}", json={"role": "data_analyst"}, headers=admin.headers)
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_reinitialisation_totp(client, account, make_user, db):
    admin = account(Role.ADMIN)
    user = make_user(Role.DIRECTEUR, email="dir@exemple.org")
    resp = client.post(f"/api/users/{user.id}/reset-mfa", headers=admin.headers)
    assert resp.json()["mfa_enabled"] is False
    db.refresh(user)
    assert user.mfa_secret is None


def test_equipes(client, account):
    admin = account(Role.ADMIN)
    auditeur = account(Role.AUDITEUR)
    assert client.post("/api/teams", json={"nom": "Paie"}, headers=admin.headers).status_code == 201
    assert client.post("/api/teams", json={"nom": "Paie"}, headers=admin.headers).status_code == 409
    teams = client.get("/api/teams", headers=auditeur.headers).json()
    assert [t["nom"] for t in teams] == ["Paie"]


def test_domaine_interne_accepte_et_email_invalide_refuse(client, account):
    h = account(Role.ADMIN).headers
    ok = client.post("/api/users", json={**NEW_USER, "email": "Awa@Cabinet.LOCAL"}, headers=h)
    assert ok.status_code == 201 and ok.json()["email"] == "awa@cabinet.local"
    bad = client.post("/api/users", json={**NEW_USER, "email": "pas-un-email"}, headers=h)
    assert bad.status_code == 422
