"""CON-05 : plans d'action."""

import datetime as dt

from tests.finding_helpers import create_finding, team  # noqa: F401


def plan(client, team, finding, **kw):  # noqa: F811
    body = {"description": "Réactiver le contrôle bloquant", "responsable_id": str(team["audite"].user.id),
            "echeance": str(dt.date.today() + dt.timedelta(days=60)), **kw}  # fmt: skip
    resp = client.post(
        f"/api/findings/{finding['id']}/action-plans", json=body, headers=team["aud"].headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def status(client, p, acc, statut, commentaire=None):
    return client.post(f"/api/action-plans/{p['id']}/status",
                       json={"statut": statut, "commentaire": commentaire}, headers=acc.headers)  # fmt: skip


def test_con05_plan_et_statuts(client, team):  # noqa: F811
    f = create_finding(client, team)
    p = plan(client, team, f)
    assert p["statut"] == "a_lancer" and p["responsable"] == team["audite"].user.nom
    assert p["constat_reference"] == "C-01" and not p["en_retard"]
    assert set(p["transitions"]) == {"en_cours", "realise"}  # le risque accepté relève du chef
    # Le responsable (audité) fait avancer son plan.
    assert status(client, p, team["audite"], "en_cours").status_code == 200
    resp = status(client, p, team["audite"], "realise", "Contrôle réactivé le 3 mars")
    assert (
        resp.json()["statut"] == "realise"
        and resp.json()["commentaire"] == "Contrôle réactivé le 3 mars"
    )
    # L'audité ne vérifie pas lui-même ; l'auditeur vérifie.
    assert status(client, p, team["audite"], "verifie").status_code == 409
    resp = status(client, p, team["aud"], "verifie")
    assert resp.json()["statut"] == "verifie" and resp.json()["verifie_le"]
    assert status(client, p, team["aud"], "en_cours").status_code == 409  # plan clos
    listed = client.get(f"{team['url']}/action-plans", headers=team["chef"].headers).json()
    assert [x["statut"] for x in listed] == ["verifie"]


def test_con05_risque_accepte_et_retard(client, team):  # noqa: F811
    f = create_finding(client, team)
    late = plan(client, team, f, echeance=str(dt.date.today() - dt.timedelta(days=1)))
    assert late["en_retard"]
    assert (
        status(client, late, team["aud"], "risque_accepte", "x").status_code == 409
    )  # chef seulement
    assert status(client, late, team["chef"], "risque_accepte").status_code == 422
    resp = status(
        client, late, team["chef"], "risque_accepte", "Coût disproportionné, accepté par la DG"
    )
    assert resp.status_code == 200 and not resp.json()["en_retard"]


def test_con05_droits_et_modifications(client, team, account):  # noqa: F811
    from app.models import Finding
    from app.security.roles import Role

    f = create_finding(client, team)
    p = plan(client, team, f, responsable_id=None, responsable_nom="Directeur des achats")
    assert p["responsable"] == "Directeur des achats"
    other = account(Role.AUDITE)
    assert status(client, p, other, "en_cours").status_code == 404
    assert client.post(f"/api/findings/{f['id']}/action-plans", json={"description": "x", "echeance": "2027-01-01"},
                       headers=team["da"].headers).status_code == 403  # fmt: skip
    bad = client.post(f"/api/findings/{f['id']}/action-plans",
                      json={"description": "x", "echeance": "2027-01-01",
                            "responsable_id": "00000000-0000-0000-0000-000000000000"},
                      headers=team["aud"].headers)  # fmt: skip
    assert bad.status_code == 422
    resp = client.patch(
        f"/api/action-plans/{p['id']}", json={"echeance": "2027-06-30"}, headers=team["aud"].headers
    )
    assert resp.json()["echeance"] == "2027-06-30"
    from app.db import SessionLocal

    with SessionLocal() as db:
        db.get(Finding, f["id"]).statut = "valide"
        db.commit()
    resp = client.patch(
        f"/api/action-plans/{p['id']}", json={"echeance": "2027-12-31"}, headers=team["aud"].headers
    )
    assert resp.status_code == 409 and "report" in resp.text
    resp = client.patch(
        f"/api/action-plans/{p['id']}", json={"description": "Nouveau"}, headers=team["aud"].headers
    )
    assert resp.status_code == 200


def test_liste_des_audites(client, team):  # noqa: F811
    listed = client.get("/api/auditees", headers=team["aud"].headers).json()
    assert [a["id"] for a in listed] == [str(team["audite"].user.id)]
    assert client.get("/api/auditees", headers=team["da"].headers).status_code == 403
