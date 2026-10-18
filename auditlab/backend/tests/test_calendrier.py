"""RCO-03 : calendrier fiscal et social par pays, alertes à J-15 et J-5."""

import datetime as dt

from sqlalchemy import func, select

from tests.portfolio_helpers import cabinet, new_client  # noqa: F401

D = dt.date
# Règles fictives : aucune valeur réglementaire n'est livrée, le cabinet les saisit.
RULES = [
    {"code": "TVA", "libelle": "Déclaration de TVA", "nature": "fiscal", "periodicite": "mensuelle", "jour": 15},
    {"code": "COT", "libelle": "Cotisations sociales", "nature": "social", "periodicite": "trimestrielle", "jour": 15},
    {"code": "PAT", "libelle": "Contribution des patentes", "nature": "fiscal", "periodicite": "annuelle", "jour": 31, "mois": 3},
    {"code": "DSF", "libelle": "Dépôt de la liasse", "nature": "fiscal", "periodicite": "cloture", "decalage_mois": 4, "jour": 30},
    {"code": "IS", "libelle": "Acompte d'impôt (réel normal)", "nature": "fiscal", "periodicite": "mensuelle", "jour": 20,
     "regimes": ["reel_normal"]},
]  # fmt: skip


def test_rco03_calendrier(client, cabinet, db):  # noqa: F811
    from app.cabinet.calendar import client_deadlines, send_calendar_alerts
    from app.models import Client, Notification

    expert, collab = cabinet["expert"], cabinet["collab"]
    c = new_client(client, cabinet)
    for rule in RULES:
        resp = client.post(
            "/api/calendar-rules", json={"pays": "CI", **rule}, headers=expert.headers
        )
        assert resp.status_code == 201, resp.text
    client.post("/api/calendar-rules", json={"pays": "SN", **RULES[0]}, headers=expert.headers)
    assert (
        client.post(
            "/api/calendar-rules", json={"pays": "CI", **RULES[0]}, headers=collab.headers
        ).status_code
        == 403
    )
    bad = {"pays": "CI", **RULES[2], "mois": None}
    assert client.post("/api/calendar-rules", json=bad, headers=expert.headers).status_code == 422
    assert len(client.get("/api/calendar-rules?pays=CI", headers=collab.headers).json()) == 5
    entity = db.get(Client, c["id"])
    items = client_deadlines(db, entity, D(2026, 1, 1), D(2026, 6, 30), today=D(2026, 4, 20))
    assert [(i["code"], i["echeance"]) for i in items if i["code"] != "TVA"] == [
        ("COT", "2026-01-15"), ("PAT", "2026-03-31"), ("COT", "2026-04-15"), ("DSF", "2026-04-30")]  # fmt: skip
    tva = [i for i in items if i["code"] == "TVA"]
    assert [i["periode"] for i in tva] == [
        "12/2025",
        "01/2026",
        "02/2026",
        "03/2026",
        "04/2026",
        "05/2026",
    ]
    assert {i["statut"] for i in items if i["echeance"] < "2026-04-20"} == {"en_retard"}
    assert next(i for i in items if i["code"] == "DSF")["statut"] == "a_venir"
    # Échéance faite (collaborateur) : elle ne donne plus lieu à alerte.
    tva_rule = tva[0]["rule_id"]
    url = f"/api/clients/{c['id']}/deadlines/{tva_rule}/2026-04-15"
    done = client.put(url, json={"fait": True, "date": "2026-04-02"}, headers=collab.headers).json()
    assert (done["statut"], done["fait_le"]) == ("fait", "2026-04-02")
    assert client.put(f"/api/clients/{c['id']}/deadlines/{tva_rule}/2026-04-16", json={"fait": True},
                      headers=collab.headers).status_code == 404  # fmt: skip

    # Alertes : à J-15, puis à J-5, jamais deux fois.
    def alerts():
        return db.scalar(select(func.count()).select_from(Notification).where(
            Notification.user_id == expert.user.id, Notification.type == "echeance"))  # fmt: skip

    assert send_calendar_alerts(db, D(2026, 4, 1)) == 1  # COT du 15/04 (la TVA est faite)
    assert send_calendar_alerts(db, D(2026, 4, 1)) == 0
    assert send_calendar_alerts(db, D(2026, 4, 10)) == 1  # COT à J-5
    assert send_calendar_alerts(db, D(2026, 4, 16)) == 1  # DSF du 30/04 à J-15 (14 jours)
    assert alerts() == 3
    assert len(client.get(f"/api/clients/{c['id']}/deadlines", headers=collab.headers).json()) > 0
    rule = client.get("/api/calendar-rules?pays=SN", headers=expert.headers).json()[0]
    assert (
        client.delete(f"/api/calendar-rules/{rule['id']}", headers=expert.headers).status_code
        == 204
    )
    assert client.get("/api/calendar-rules?pays=SN", headers=expert.headers).json() == []
