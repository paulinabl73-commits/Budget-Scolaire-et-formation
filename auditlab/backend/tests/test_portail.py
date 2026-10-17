"""CON-09 : portail audité, limité à ses constats et plans d'action."""

import io

import polars as pl

from tests.data_helpers import make_dataset
from tests.finding_helpers import create_finding, team  # noqa: F401


def test_con09_portail(client, team, db, account):  # noqa: F811
    from app.security.roles import Role

    audite = team["audite"]
    sent = create_finding(client, team, titre="Envoyé")
    create_finding(client, team, titre="Brouillon")  # jamais visible
    client.post(
        f"/api/findings/{sent['id']}/send",
        json={"audite_id": str(audite.user.id)},
        headers=team["aud"].headers,
    )
    # Constat d'un autre audité, mais dont notre audité porte un plan.
    other = account(Role.AUDITE)
    shared = create_finding(client, team, titre="Partagé")
    client.post(
        f"/api/findings/{shared['id']}/send",
        json={"audite_id": str(other.user.id)},
        headers=team["aud"].headers,
    )
    client.post(f"/api/findings/{shared['id']}/action-plans",
                json={"description": "Plan", "echeance": "2099-01-01", "responsable_id": str(audite.user.id)},
                headers=team["aud"].headers)  # fmt: skip

    listed = client.get("/api/portal/findings", headers=audite.headers).json()
    assert sorted(f["titre"] for f in listed) == ["Envoyé", "Partagé"]
    mine = next(f for f in listed if f["titre"] == "Envoyé")
    assert mine["peut_repondre"] and mine["mission"]["reference"] == team["mission"]["reference"]
    assert "workpaper_ids" not in mine and "audite_id" not in mine  # rien d'interne
    assert not next(f for f in listed if f["titre"] == "Partagé")["peut_repondre"]
    # Réponse depuis le portail, avec plan proposé.
    body = {
        "position": "accord",
        "plans": [{"description": "Former les acheteurs", "echeance": "2027-09-30"}],
    }
    resp = client.post(
        f"/api/portal/findings/{sent['id']}/response", json=body, headers=audite.headers
    )
    assert resp.status_code == 200 and resp.json()["statut"] == "repondu"
    detail = client.get(f"/api/portal/findings/{sent['id']}", headers=audite.headers).json()
    assert [p["description"] for p in detail["plans"]] == ["Former les acheteurs"]
    assert "en_cours" in detail["plans"][0]["transitions"]
    assert client.post(f"/api/portal/findings/{shared['id']}/response", json={"position": "accord"},
                       headers=audite.headers).status_code == 403  # fmt: skip
    # Justificatif déposé depuis le portail sur son plan.
    plan_id = detail["plans"][0]["id"]
    up = client.post(f"/api/action-plans/{plan_id}/evidence", files={"file": ("pv.txt", io.BytesIO(b"ok"))},
                     headers=audite.headers)  # fmt: skip
    assert up.status_code == 201


def test_con09_rien_d_autre(client, team, db, account):  # noqa: F811
    from app.security.roles import Role

    audite = team["audite"]
    f = create_finding(client, team)
    ds = make_dataset(db, team["mission"]["id"], pl.DataFrame({"a": [1]}))
    for path in (
        f"/api/findings/{f['id']}",
        f"/api/portal/findings/{f['id']}",  # brouillon
        f"{team['url']}",
        f"{team['url']}/findings",
        f"/api/workpapers/{team['wp']['id']}",
        f"/api/datasets/{ds.id}",
        "/api/engagements",
        "/api/universe/entities",
        "/api/auditees",
        "/api/audit-log",
    ):
        assert client.get(path, headers=audite.headers).status_code in (403, 404), path
    # Les autres rôles n'ont pas de portail.
    assert client.get("/api/portal/findings", headers=team["aud"].headers).status_code == 403
    stranger = account(Role.AUDITE)
    assert client.get("/api/portal/findings", headers=stranger.headers).json() == []
