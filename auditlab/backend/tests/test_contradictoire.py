"""CON-04 : phase contradictoire."""

import datetime as dt

from tests.finding_helpers import create_finding, team  # noqa: F401


def advance(client, team, *statuts):  # noqa: F811
    for s in statuts:
        resp = client.post(
            f"{team['url']}/status", json={"statut": s}, headers=team["chef"].headers
        )
        if resp.status_code != 200:
            return resp
    return resp


def test_con04_envoi_reponse_validation(client, team, db):  # noqa: F811
    from sqlalchemy import select

    from app.models import ActionPlan, Notification

    f = create_finding(client, team)
    url = f"/api/findings/{f['id']}"
    audite = team["audite"]
    resp = client.post(
        f"{url}/send", json={"audite_id": str(audite.user.id)}, headers=team["aud"].headers
    )
    assert resp.status_code == 200, resp.text
    sent = resp.json()
    assert sent["statut"] == "envoye" and sent["audite_nom"] == audite.user.nom
    assert sent["date_limite_reponse"] == str(dt.date.today() + dt.timedelta(days=15))
    assert not sent["peut_modifier"]  # le texte est figé pendant la phase contradictoire
    note = db.scalar(select(Notification).where(Notification.user_id == audite.user.id))
    assert note.lien == f"/portail/constats/{f['id']}"
    # Réponse : désaccord partiel motivé et plan proposé.
    body = {"position": "accord_partiel", "commentaire": "8 créations sur 12 étaient urgentes",
            "plans": [{"description": "Réactiver le blocage", "echeance": "2027-06-30"}]}  # fmt: skip
    assert (
        client.post(
            f"{url}/response", json={**body, "commentaire": ""}, headers=audite.headers
        ).status_code
        == 422
    )
    assert client.post(f"{url}/response", json=body, headers=team["aud"].headers).status_code == 404
    resp = client.post(f"{url}/response", json=body, headers=audite.headers)
    assert resp.status_code == 200 and resp.json()["statut"] == "repondu"
    plans = db.scalars(select(ActionPlan).where(ActionPlan.finding_id == f["id"])).all()
    assert (
        len(plans) == 1
        and plans[0].propose_par_audite
        and plans[0].responsable_id == audite.user.id
    )
    assert client.post(f"{url}/response", json=body, headers=audite.headers).status_code == 409
    # L'équipe peut encore ajuster le texte, puis le chef valide.
    assert (
        client.patch(
            url, json={"cause": "Urgences non tracées"}, headers=team["aud"].headers
        ).status_code
        == 200
    )
    assert client.post(f"{url}/validate", json={}, headers=team["aud"].headers).status_code == 403
    resp = client.post(
        f"{url}/validate", json={"commentaire": "Position retenue"}, headers=team["chef"].headers
    )
    assert resp.status_code == 200 and resp.json()["statut"] == "valide"
    assert client.patch(url, json={"cause": "x"}, headers=team["aud"].headers).status_code == 409


def test_con04_controles_et_sans_reponse(client, team, db, account):  # noqa: F811
    from app.models import Finding
    from app.security.roles import Role

    f = create_finding(client, team, recommandation=None)
    url = f"/api/findings/{f['id']}"
    aid = str(team["audite"].user.id)
    resp = client.post(f"{url}/send", json={"audite_id": aid}, headers=team["aud"].headers)
    assert resp.status_code == 422 and "recommandation" in resp.text
    client.patch(url, json={"recommandation": "Revoir les créations"}, headers=team["aud"].headers)
    not_audite = str(team["da"].user.id)
    assert (
        client.post(
            f"{url}/send", json={"audite_id": not_audite}, headers=team["aud"].headers
        ).status_code
        == 422
    )
    past = {"audite_id": aid, "date_limite_reponse": "2020-01-01"}
    assert client.post(f"{url}/send", json=past, headers=team["aud"].headers).status_code == 422
    assert (
        client.post(f"{url}/send", json={"audite_id": aid}, headers=team["aud"].headers).status_code
        == 200
    )
    assert (
        client.post(f"{url}/send", json={"audite_id": aid}, headers=team["aud"].headers).status_code
        == 409
    )
    # Un autre audité ne peut pas répondre.
    other = account(Role.AUDITE)
    assert (
        client.post(
            f"{url}/response", json={"position": "accord"}, headers=other.headers
        ).status_code
        == 404
    )
    # Pas de validation avant la date limite sans réponse ; possible ensuite.
    assert client.post(f"{url}/validate", json={}, headers=team["chef"].headers).status_code == 409
    finding = db.get(Finding, f["id"])
    finding.date_limite_reponse = dt.date.today() - dt.timedelta(days=1)
    db.commit()
    resp = client.post(f"{url}/validate", json={}, headers=team["directeur"].headers)
    assert resp.status_code == 200 and resp.json()["reponse_position"] == "sans_reponse"


def test_con04_passage_en_rapport(client, team):  # noqa: F811
    f = create_finding(client, team)
    resp = advance(client, team, "preparation", "terrain", "revue", "rapport")
    assert resp.status_code == 409 and "C-01 non validé" in resp.text
    url = f"/api/findings/{f['id']}"
    client.post(
        f"{url}/send", json={"audite_id": str(team["audite"].user.id)}, headers=team["aud"].headers
    )
    client.post(f"{url}/response", json={"position": "accord"}, headers=team["audite"].headers)
    client.post(f"{url}/validate", json={}, headers=team["chef"].headers)
    assert advance(client, team, "rapport").status_code == 200
