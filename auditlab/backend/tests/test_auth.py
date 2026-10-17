from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import select, update

from app.models import AuditLog, User, UserSession
from app.security.roles import Role
from tests.conftest import PASSWORD, login


def _login(client, email, password=PASSWORD, code=None):
    body = {"email": email, "password": password}
    if code:
        body["totp_code"] = code
    return client.post("/api/auth/login", json=body)


def test_connexion_et_profil(client, make_user):
    user = make_user(Role.AUDITEUR)
    headers = login(client, user)
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == user.email
    assert me["role"] == "auditeur"
    assert "data:analyze" in me["permissions"]
    assert me["mfa_required"] is False


def test_mot_de_passe_stocke_en_argon2(make_user):
    assert make_user().password_hash.startswith("$argon2id$")


def test_identifiants_incorrects(client, make_user, db):
    user = make_user()
    assert _login(client, user.email, "mauvais").status_code == 401
    assert _login(client, "inconnu@exemple.org").status_code == 401
    actions = db.scalars(select(AuditLog.action).where(AuditLog.action == "login_failed")).all()
    assert len(actions) == 2


def test_verrouillage_apres_cinq_echecs(client, make_user, account, db):
    user = make_user()
    for _ in range(5):
        assert _login(client, user.email, "mauvais").status_code == 401
    resp = _login(client, user.email)
    assert resp.status_code == 423
    db.refresh(user)
    assert user.is_locked

    admin = account(Role.ADMIN)
    resp = client.post(f"/api/users/{user.id}/unlock", headers=admin.headers)
    assert resp.status_code == 200 and resp.json()["is_locked"] is False
    assert _login(client, user.email).status_code == 200


def test_session_expiree_apres_inactivite(client, make_user, db):
    user = make_user()
    headers = login(client, user)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    db.execute(update(UserSession).values(last_seen_at=datetime.now(UTC) - timedelta(minutes=31)))
    db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    # Une session expirée le reste.
    db.execute(update(UserSession).values(last_seen_at=datetime.now(UTC)))
    db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_jeton_absent_ou_invalide(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer faux"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Basic x"}).status_code == 401


def test_deconnexion(client, make_user):
    headers = login(client, make_user())
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_compte_desactive(client, make_user, db):
    user = make_user()
    headers = login(client, user)
    user.actif = False
    db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert _login(client, user.email).status_code == 401


def test_double_authentification_exigee_pour_directeur(client, make_user):
    user = make_user(Role.DIRECTEUR)
    resp = _login(client, user.email)
    assert resp.status_code == 401 and resp.json()["detail"] == "mfa_required"
    assert _login(client, user.email, code="000000").status_code == 401
    resp = _login(client, user.email, code=pyotp.TOTP(user.mfa_secret).now())
    assert resp.status_code == 200 and resp.json()["mfa_enrollment_required"] is False


def test_code_totp_faux_compte_comme_un_echec(client, make_user, db):
    user = make_user(Role.ADMIN)
    for _ in range(5):
        _login(client, user.email, code="123456")
    db.refresh(user)
    assert user.is_locked


def test_enrolement_totp_obligatoire_pour_administrateur(client, make_user):
    user = make_user(Role.ADMIN, mfa=False)
    resp = _login(client, user.email)
    assert resp.status_code == 200 and resp.json()["mfa_enrollment_required"] is True
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    # Tant que le TOTP n'est pas activé, seules les routes d'enrôlement sont ouvertes.
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    setup = client.post("/api/auth/mfa/setup", headers=headers).json()
    assert client.post("/api/auth/mfa/setup", headers=headers).json() == setup
    assert setup["provisioning_uri"].startswith("otpauth://totp/AuditLab:")
    bad = client.post("/api/auth/mfa/activate", json={"code": "abc"}, headers=headers)
    assert bad.status_code == 400
    code = pyotp.TOTP(setup["secret"]).now()
    resp = client.post("/api/auth/mfa/activate", json={"code": code}, headers=headers)
    assert resp.status_code == 200 and resp.json()["mfa_enabled"] is True
    assert client.get("/api/users", headers=headers).status_code == 200
    assert client.post("/api/auth/mfa/setup", headers=headers).status_code == 409
    assert (
        client.post("/api/auth/mfa/activate", json={"code": code}, headers=headers).status_code
        == 409
    )


def test_changement_de_mot_de_passe(client, make_user, db):
    user = make_user()
    headers = login(client, user)
    other = login(client, user)
    url = "/api/auth/password"
    bad = client.post(
        url, json={"current_password": "x", "new_password": "Nouveau-Mdp-2026"}, headers=headers
    )
    assert bad.status_code == 400
    weak = client.post(
        url, json={"current_password": PASSWORD, "new_password": "court"}, headers=headers
    )
    assert weak.status_code == 422
    ok = client.post(
        url,
        json={"current_password": PASSWORD, "new_password": "Nouveau-Mdp-2026"},
        headers=headers,
    )
    assert ok.status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=other).status_code == 401
    assert _login(client, user.email, "Nouveau-Mdp-2026").status_code == 200


def test_connexion_insensible_a_la_casse(client, make_user):
    user = make_user(email="Marie.Kone@exemple.org")
    assert _login(client, "marie.kone@EXEMPLE.org").status_code == 200
    assert isinstance(user, User)
