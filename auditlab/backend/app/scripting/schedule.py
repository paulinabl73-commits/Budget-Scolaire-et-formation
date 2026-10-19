"""Audit en continu (DAT-29) : exécution planifiée d'un script, chaque jour ou chaque mois à
l'heure choisie (UTC), et alerte quand un indicateur dépasse son seuil.

Une exécution planifiée en erreur, ou qui ne produit pas l'indicateur surveillé, alerte aussi :
un contrôle continu silencieux ne doit pas passer pour un contrôle satisfaisant. Les
destinataires sont le chef de mission et l'auteur du script. Les missions clôturées ne sont
plus exécutées.
"""

import datetime as dt
import operator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data import Script, ScriptRun
from app.models.engagement import Engagement, MissionRole
from app.notify import notify

OPERATORS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
             "!=": operator.ne}  # fmt: skip


def next_run(plan: dict[str, Any], after: dt.datetime) -> dt.datetime:
    """Première échéance strictement postérieure à `after`."""
    hour = int(plan.get("heure", 6))
    if plan["frequence"] == "quotidienne":
        candidate = after.replace(hour=hour, minute=0, second=0, microsecond=0)
        return candidate if candidate > after else candidate + dt.timedelta(days=1)
    day = int(plan.get("jour", 1))
    candidate = after.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)
    if candidate > after:
        return candidate
    year, month = (after.year + 1, 1) if after.month == 12 else (after.year, after.month + 1)
    return candidate.replace(year=year, month=month)


def alert_of(plan: dict[str, Any] | None, run: ScriptRun) -> str | None:
    if run.statut == "erreur":
        return f"Exécution en erreur : {(run.erreur or '').splitlines()[0][:200]}"
    rule = (plan or {}).get("alerte")
    if not rule:
        return None
    name = rule["indicateur"]
    if name not in run.indicateurs:
        return f"Indicateur « {name} » non produit par le script"
    value, seuil = float(run.indicateurs[name]), float(rule["seuil"])
    if OPERATORS[rule["operateur"]](value, seuil):
        return f"{name} = {value:g} ({rule['operateur']} {seuil:g})"
    return None


def after_run(db: Session, run: ScriptRun) -> None:
    """Alerte d'une exécution planifiée terminée (appelée par la tâche d'exécution)."""
    if run.declenchement != "planifie":
        return
    script = db.get(Script, run.script_id)
    run.alerte = alert_of(script.planification, run)
    if run.alerte is None:
        return
    engagement = db.get(Engagement, script.engagement_id)
    chefs = {m.user_id for m in engagement.members if m.role_mission == MissionRole.CHEF}
    notify(
        db,
        chefs | {script.created_by},
        "alerte_script",
        f"Alerte du script « {script.nom} »",
        f"{engagement.reference} – {run.alerte}",
        lien=f"/missions/{engagement.id}/scripts/{script.id}",
    )


def run_due(db: Session, now: dt.datetime | None = None) -> int:
    """Lance les scripts dont l'échéance est passée et fixe leur prochaine échéance."""
    from app.api.scripts import start_run

    now = now or dt.datetime.now(dt.UTC)
    due = list(
        db.scalars(
            select(Script)
            .join(Engagement, Engagement.id == Script.engagement_id)
            .where(
                Script.prochaine_execution <= now,
                Script.deleted_at.is_(None),
                Engagement.statut != "cloturee",
                Engagement.deleted_at.is_(None),
            )
        )
    )
    for script in due:
        script.prochaine_execution = next_run(script.planification, now)
        start_run(db, script, script.created_by, "planifie")
    return len(due)
