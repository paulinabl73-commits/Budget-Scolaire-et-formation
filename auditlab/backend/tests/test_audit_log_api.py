import pytest

from app.security.roles import Role


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTEUR])
def test_lecture_du_journal_autorisee(client, account, role):
    acc = account(role)
    page = client.get("/api/audit-log", headers=acc.headers).json()
    assert page["total"] >= 2
    assert page["items"][0]["seq"] > page["items"][-1]["seq"]
    login_entry = next(e for e in page["items"] if e["action"] == "login")
    assert login_entry["user_nom"] == acc.user.nom


@pytest.mark.parametrize("role", [Role.CHEF_MISSION, Role.AUDITEUR, Role.DATA_ANALYST, Role.AUDITE])
def test_lecture_du_journal_refusee(client, account, role):
    h = account(role).headers
    assert client.get("/api/audit-log", headers=h).status_code == 403
    assert client.get("/api/audit-log/verify", headers=h).status_code == 403


def test_filtres_et_pagination(client, account):
    admin = account(Role.ADMIN)
    h = admin.headers
    base = "/api/audit-log"
    created = client.get(base, params={"action": "create"}, headers=h).json()
    assert created["total"] == 1 and created["items"][0]["object_type"] == "User"
    by_obj = client.get(
        base, params={"object_type": "User", "object_id": str(admin.user.id)}, headers=h
    ).json()
    assert by_obj["total"] >= 1
    by_user = client.get(base, params={"user_id": str(admin.user.id)}, headers=h).json()
    assert all(e["user_id"] == str(admin.user.id) for e in by_user["items"])
    dated = client.get(
        base,
        params={"depuis": "2000-01-01T00:00:00Z", "jusqu_a": "2999-01-01T00:00:00Z"},
        headers=h,
    ).json()
    page = client.get(base, params={"limit": 1, "offset": 1}, headers=h).json()
    assert len(page["items"]) == 1 and page["total"] == dated["total"]


def test_verification_via_api(client, account):
    h = account(Role.ADMIN).headers
    report = client.get("/api/audit-log/verify", headers=h).json()
    assert report["ok"] is True and report["entries"] >= 2
    last = client.get("/api/audit-log", params={"limit": 1}, headers=h).json()["items"][0]
    assert last["action"] == "audit_chain_verified"
