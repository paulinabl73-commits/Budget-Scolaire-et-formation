"""CON-06 : relances automatiques des plans d'action."""

import datetime as dt

from sqlalchemy import select

from app.followup import due_reminder, send_reminders
from app.models import ActionPlan, EmailMessage, Notification
from tests.finding_helpers import create_finding, team  # noqa: F401


def test_calendrier_des_relances():
    plan = ActionPlan(echeance=dt.date(2027, 6, 30), relances=[])
    d = dt.date
    assert due_reminder(plan, d(2027, 6, 14)) is None
    assert due_reminder(plan, d(2027, 6, 15)) == "j15"
    plan.relances = [{"type": "j15", "date": "2027-06-15"}]
    assert due_reminder(plan, d(2027, 6, 20)) is None
    assert due_reminder(plan, d(2027, 6, 30)) == "echeance"
    plan.relances.append({"type": "echeance", "date": "2027-06-30"})
    assert due_reminder(plan, d(2027, 7, 13)) is None
    assert due_reminder(plan, d(2027, 7, 14)) == "retard"
    plan.relances.append({"type": "retard", "date": "2027-07-14"})
    assert due_reminder(plan, d(2027, 7, 27)) is None
    assert due_reminder(plan, d(2027, 7, 28)) == "retard"
    # Plan créé après J-15 : relance immédiate, puis à l'échéance.
    late = ActionPlan(echeance=d(2027, 6, 30), relances=[])
    assert due_reminder(late, d(2027, 6, 25)) == "j15"
    # Plan découvert après l'échéance : relance « échéance » d'abord.
    assert (
        due_reminder(ActionPlan(echeance=d(2027, 6, 30), relances=[]), d(2027, 8, 1)) == "echeance"
    )


def test_con06_envoi_et_unicite(client, team, db):  # noqa: F811
    f = create_finding(client, team)
    today = dt.date.today()
    body = {"description": "Réactiver le contrôle", "responsable_id": str(team["audite"].user.id),
            "echeance": str(today + dt.timedelta(days=10))}  # fmt: skip
    plan_id = client.post(
        f"/api/findings/{f['id']}/action-plans", json=body, headers=team["aud"].headers
    ).json()["id"]
    done = client.post(f"/api/findings/{f['id']}/action-plans",
                       json={**body, "echeance": str(today - dt.timedelta(days=30))}, headers=team["aud"].headers).json()  # fmt: skip
    client.post(
        f"/api/action-plans/{done['id']}/status",
        json={"statut": "realise"},
        headers=team["audite"].headers,
    )
    assert send_reminders(db, today) == 1  # le plan réalisé n'est plus relancé
    assert send_reminders(db, today) == 0  # une seule relance par jour et par type
    db.expire_all()
    plan = db.get(ActionPlan, plan_id)
    assert plan.relances == [{"type": "j15", "date": today.isoformat()}]
    note = db.scalar(select(Notification).where(Notification.type == "plan_relance_j15"))
    assert note.user_id == team["audite"].user.id and "C-01" in note.titre
    assert (
        db.scalar(
            select(EmailMessage).where(EmailMessage.destinataire == team["audite"].user.email)
        )
        is not None
    )
    # En retard : le chef de mission est aussi prévenu.
    later = today + dt.timedelta(days=10)
    assert send_reminders(db, later) == 1
    assert send_reminders(db, later + dt.timedelta(days=14)) == 1
    chef_notes = db.scalars(select(Notification).where(Notification.user_id == team["chef"].user.id,
                                                       Notification.type == "plan_relance_retard")).all()  # fmt: skip
    assert len(chef_notes) == 1


def test_commande_send_reminders(capsys):
    from app.cli import main

    assert main(["send-reminders"]) == 0
    assert "relance(s)" in capsys.readouterr().out
