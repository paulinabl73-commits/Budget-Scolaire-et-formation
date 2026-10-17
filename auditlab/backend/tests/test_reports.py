"""CON-08 : report d'échéance soumis au chef de mission, avec historique."""

import datetime as dt

from app.models import ActionPlan
from tests.finding_helpers import create_finding, team  # noqa: F401
from tests.test_justificatifs import setup_plan


def test_con08_demande_et_decisions(client, team, db):  # noqa: F811
    _, plan = setup_plan(client, team)
    url = f"/api/action-plans/{plan['id']}/postponements"
    current = dt.date.fromisoformat(plan["echeance"])
    audite = team["audite"]
    later = str(current + dt.timedelta(days=30))
    assert client.post(url, json={"nouvelle_echeance": plan["echeance"], "motif": "x"},
                       headers=audite.headers).status_code == 422  # fmt: skip
    first = client.post(
        url,
        json={"nouvelle_echeance": later, "motif": "Budget non disponible"},
        headers=audite.headers,
    )
    assert first.status_code == 201 and first.json()["statut"] == "demande"
    assert (
        client.post(
            url, json={"nouvelle_echeance": later, "motif": "x"}, headers=audite.headers
        ).status_code
        == 409
    )
    decision = f"/api/postponements/{first.json()['id']}/decision"
    assert (
        client.post(decision, json={"decision": "refuse"}, headers=team["aud"].headers).status_code
        == 403
    )
    resp = client.post(decision, json={"decision": "refuse", "commentaire": "Priorité maintenue"},
                       headers=team["chef"].headers)  # fmt: skip
    assert resp.json()["statut"] == "refuse" and resp.json()["decide_par"] == team["chef"].user.nom
    assert (
        client.post(
            decision, json={"decision": "accepte"}, headers=team["chef"].headers
        ).status_code
        == 409
    )
    # Deuxième demande, acceptée : l'échéance change et les relances repartent de zéro.
    plan_row = db.get(ActionPlan, plan["id"])
    plan_row.relances = [{"type": "j15", "date": str(dt.date.today())}]
    db.commit()
    second = client.post(url, json={"nouvelle_echeance": later, "motif": "Prestataire en retard"},
                         headers=team["aud"].headers).json()  # fmt: skip
    resp = client.post(f"/api/postponements/{second['id']}/decision", json={"decision": "accepte"},
                       headers=team["directeur"].headers)  # fmt: skip
    assert resp.status_code == 200
    db.expire_all()
    plan_row = db.get(ActionPlan, plan["id"])
    assert str(plan_row.echeance) == later and plan_row.relances == []
    history = client.get(url, headers=audite.headers).json()
    assert [h["statut"] for h in history] == ["refuse", "accepte"]
    assert (
        history[0]["demande_par"] == audite.user.nom
        and history[1]["ancienne_echeance"] == plan["echeance"]
    )


def test_con08_controles(client, team, account):  # noqa: F811
    from app.security.roles import Role

    _, plan = setup_plan(client, team)
    url = f"/api/action-plans/{plan['id']}/postponements"
    body = {"nouvelle_echeance": "2099-01-01", "motif": "x"}
    assert client.post(url, json=body, headers=account(Role.AUDITE).headers).status_code == 404
    assert client.post(url, json=body, headers=team["da"].headers).status_code == 403
    assert client.post("/api/postponements/00000000-0000-0000-0000-000000000000/decision",
                       json={"decision": "accepte"}, headers=team["chef"].headers).status_code == 404  # fmt: skip
