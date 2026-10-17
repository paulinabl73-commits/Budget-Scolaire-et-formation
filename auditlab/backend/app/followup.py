"""Relances automatiques des plans d'action (CON-06).

Pour chaque plan ouvert (À lancer ou En cours), une relance part :
- à J-15 (paramétrable) avant l'échéance ;
- à l'échéance ;
- puis toutes les deux semaines (paramétrable) tant que le plan est en retard.
Chaque relance est notée dans le plan : relancer la commande le même jour n'envoie rien de plus.
À lancer chaque jour : `python -m app.cli send-reminders` (ou la tâche planifiée Celery).
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.engagement import Engagement, MissionRole
from app.models.finding import ActionPlan, ActionPlanStatus, Finding
from app.notify import notify

OPEN = (ActionPlanStatus.A_LANCER.value, ActionPlanStatus.EN_COURS.value)


def due_reminder(plan: ActionPlan, today: dt.date) -> str | None:
    s = get_settings()
    sent = {r["type"]: dt.date.fromisoformat(r["date"]) for r in plan.relances}
    last_late = max(
        (
            dt.date.fromisoformat(r["date"])
            for r in plan.relances
            if r["type"] in ("echeance", "retard")
        ),
        default=None,
    )
    if today < plan.echeance:
        if today >= plan.echeance - dt.timedelta(days=s.relance_avant_echeance_jours) and (
            "j15" not in sent
        ):
            return "j15"
        return None
    if "echeance" not in sent:
        return "echeance"
    if last_late is not None and today >= last_late + dt.timedelta(days=s.relance_retard_jours):
        return "retard"
    return None


MESSAGES = {
    "j15": "arrive à échéance le {echeance}",
    "echeance": "arrive à échéance aujourd'hui ({echeance})",
    "retard": "est en retard depuis le {echeance}",
}


def send_reminders(db: Session, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    plans = db.scalars(
        select(ActionPlan).where(ActionPlan.statut.in_(OPEN), ActionPlan.deleted_at.is_(None))
    ).all()
    count = 0
    for plan in plans:
        kind = due_reminder(plan, today)
        if kind is None:
            continue
        finding = db.get(Finding, plan.finding_id)
        if finding is None or finding.deleted_at:
            continue
        engagement = db.get(Engagement, finding.engagement_id)
        recipients: set[uuid.UUID] = {u for u in (plan.responsable_id, finding.audite_id) if u}
        if kind == "retard":  # le chef de mission suit les retards
            recipients |= {
                m.user_id for m in engagement.members if m.role_mission == MissionRole.CHEF
            }
        text = MESSAGES[kind].format(echeance=f"{plan.echeance:%d/%m/%Y}")
        notify(
            db,
            recipients,
            f"plan_relance_{kind}",
            f"Plan d'action {finding.reference} : {text}",
            f"Le plan d'action « {plan.description[:200]} » (constat « {finding.titre} », "
            f"mission {engagement.reference}) {text}. Mettez à jour son avancement et déposez vos "
            "justificatifs dans le portail.",
            lien=f"/portail/constats/{finding.id}",
        )
        plan.relances = [*plan.relances, {"type": kind, "date": today.isoformat()}]
        count += 1
    db.commit()
    return count
