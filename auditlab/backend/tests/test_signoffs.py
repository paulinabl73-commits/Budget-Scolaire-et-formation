import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.richtext import from_plain_text
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def team(client, account):
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    aud2 = account(Role.AUDITEUR)
    sup = account(Role.DIRECTEUR)
    m = helpers.mission(
        client,
        chef.headers,
        membres=[(aud.user, "auditeur"), (aud2.user, "auditeur"), (sup.user, "superviseur")],
    )
    return {
        "chef": chef,
        "aud": aud,
        "aud2": aud2,
        "sup": sup,
        "mission": m,
        "url": f"/api/engagements/{m['id']}",
    }


def ready_workpaper(client, team, acc=None):
    acc = acc or team["aud"]
    resp = client.post(
        f"{team['url']}/workpapers",
        json={
            "reference": "A-1",
            "titre": "Revue des créations",
            "travaux": from_plain_text("Tests"),
            "conclusion": "Contrôle opérant",
            "evaluation": "efficace",
        },
        headers=acc.headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def sign(client, wp, acc, kind):
    return client.post(
        f"/api/workpapers/{wp['id']}/signoffs", json={"type": kind}, headers=acc.headers
    )


def test_aud18_circuit_complet(client, team, db):
    wp = ready_workpaper(client, team)
    assert wp["statut_signature"] == "brouillon"
    assert wp["signatures_possibles"] == ["prepare"]
    assert "revu" in wp["motifs_refus"]

    resp = sign(client, wp, team["aud"], "prepare")
    assert resp.status_code == 201
    prep = resp.json()
    assert prep["user_nom"] == team["aud"].user.nom and prep["version"] == 1
    assert len(prep["hash_contenu"]) == 64 and prep["signed_at"]

    assert sign(client, wp, team["chef"], "revu").status_code == 201
    assert sign(client, wp, team["chef"], "approuve").status_code == 201
    detail = client.get(f"/api/workpapers/{wp['id']}", headers=team["aud"].headers).json()
    assert detail["statut_signature"] == "approuve"
    assert [s["type"] for s in detail["signatures"]] == ["prepare", "revu", "approuve"]
    listed = client.get(f"{team['url']}/workpapers", headers=team["aud"].headers).json()
    assert listed[0]["statut_signature"] == "approuve"
    actions = db.scalars(select(AuditLog.action).where(AuditLog.object_type == "Signoff")).all()
    assert actions == ["create", "create", "create"]


def test_aud18_ordre_et_conditions(client, team):
    resp = client.post(
        f"{team['url']}/workpapers",
        json={"reference": "A-2", "titre": "Sans conclusion"},
        headers=team["aud"].headers,
    )
    wp = resp.json()
    r = sign(client, wp, team["aud"], "prepare")
    assert r.status_code == 409 and "Conclusion" in r.json()["detail"]
    wp = ready_workpaper(client, team)
    assert sign(client, wp, team["chef"], "revu").status_code == 409  # pas encore préparé
    sign(client, wp, team["aud"], "prepare")
    assert sign(client, wp, team["aud"], "prepare").status_code == 409  # déjà signé
    assert sign(client, wp, team["chef"], "approuve").status_code == 409  # pas encore revu


def test_aud18_separation_des_taches(client, team):
    # Le chef prépare : ni lui ni un auditeur ne revoient ; le superviseur (Directeur) le peut.
    wp = ready_workpaper(client, team, acc=team["chef"])
    sign(client, wp, team["chef"], "prepare")
    r = sign(client, wp, team["chef"], "revu")
    assert r.status_code == 403 and "Séparation des tâches" in r.json()["detail"]
    r = sign(client, wp, team["aud2"], "revu")
    assert r.status_code == 403 and "chef de mission" in r.json()["detail"]
    assert sign(client, wp, team["sup"], "revu").status_code == 201
    # Approbation : pas par le préparateur ; le Directeur peut approuver.
    r = sign(client, wp, team["chef"], "approuve")
    assert r.status_code == 403 and "Séparation" in r.json()["detail"]
    assert sign(client, wp, team["sup"], "approuve").status_code == 201
    history = client.get(f"/api/workpapers/{wp['id']}/signoffs", headers=team["aud"].headers).json()
    assert [(s["type"], s["user_nom"]) for s in history] == [
        ("prepare", team["chef"].user.nom),
        ("revu", team["sup"].user.nom),
        ("approuve", team["sup"].user.nom),
    ]


def test_aud18_auditeur_ne_revoit_pas(client, team):
    wp = ready_workpaper(client, team)
    sign(client, wp, team["aud"], "prepare")
    assert sign(client, wp, team["aud2"], "revu").status_code == 403
    assert sign(client, wp, team["aud2"], "approuve").status_code == 409
