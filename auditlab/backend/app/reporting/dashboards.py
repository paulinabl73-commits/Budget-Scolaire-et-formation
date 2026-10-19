"""Tableaux de bord (REP-04 à REP-06, REP-08) : calculs à partir des données de gestion.

Filtres communs : période (missions dont les dates recoupent la période), entité (l'entité et
ses descendants dans l'univers d'audit), criticité (constats). Seules les missions d'audit
visibles par l'utilisateur sont comptées.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.api.mission_access import visible_engagements
from app.api.timesheets import consumed_days
from app.models.engagement import STATUS_ORDER, Engagement
from app.models.plan import AuditPlan, PlanItem, PlanStatus
from app.models.universe import AuditableEntity
from app.models.user import User


@dataclass
class Filters:
    debut: dt.date | None = None
    fin: dt.date | None = None
    entity_id: uuid.UUID | None = None
    criticite: str | None = None

    def describe(self) -> dict[str, Any]:
        return {"debut": self.debut.isoformat() if self.debut else None,
                "fin": self.fin.isoformat() if self.fin else None,
                "entity_id": str(self.entity_id) if self.entity_id else None,
                "criticite": self.criticite}  # fmt: skip


def subtree(db: Session, entity_id: uuid.UUID) -> set[uuid.UUID]:
    """L'entité et tous ses descendants."""
    rows = db.execute(select(AuditableEntity.id, AuditableEntity.parent_id).where(
        AuditableEntity.deleted_at.is_(None))).all()  # fmt: skip
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for eid, parent in rows:
        children.setdefault(parent, []).append(eid)
    out, stack = set(), [entity_id]
    while stack:
        current = stack.pop()
        if current not in out:
            out.add(current)
            stack += children.get(current, [])
    return out


def missions(db: Session, user: User, f: Filters) -> Select[tuple[Engagement]]:
    query = visible_engagements(user).where(Engagement.mode == "audit")
    if f.debut:
        query = query.where(Engagement.date_fin >= f.debut)
    if f.fin:
        query = query.where(Engagement.date_debut <= f.fin)
    if f.entity_id:
        query = query.where(Engagement.entity_id.in_(subtree(db, f.entity_id)))
    return query


def direction(db: Session, user: User, f: Filters) -> dict[str, Any]:
    """REP-04 : avancement du plan annuel, missions par statut, jours consommés et budget."""
    rows = list(db.scalars(missions(db, user, f).order_by(Engagement.date_debut)))
    used = consumed_days(db, [e.id for e in rows])
    by_status = {s.value: 0 for s in STATUS_ORDER}
    for e in rows:
        by_status[e.statut] += 1
    budget = sum(e.budget_jours for e in rows)
    consumed = round(sum(used.get(e.id, 0.0) for e in rows), 2)
    year = (f.debut or f.fin or dt.date.today()).year
    plan = db.scalar(
        select(AuditPlan)
        .where(AuditPlan.annee == year, AuditPlan.statut == PlanStatus.VALIDE.value,
               AuditPlan.deleted_at.is_(None))
        .order_by(AuditPlan.version.desc())
        .limit(1)
    )  # fmt: skip
    plan_out = None
    if plan is not None:
        items = list(db.scalars(select(PlanItem).where(
            PlanItem.plan_id == plan.id, PlanItem.deleted_at.is_(None))))  # fmt: skip
        if f.entity_id:
            scope = subtree(db, f.entity_id)
            items = [i for i in items if i.entity_id in scope]
        linked_query = select(Engagement).where(
            Engagement.plan_item_id.in_([i.id for i in items]), Engagement.deleted_at.is_(None)
        )
        linked = {e.plan_item_id: e for e in db.scalars(linked_query)}
        closed = sum(1 for i in items if i.id in linked and linked[i.id].statut == "cloturee")
        started = sum(1 for i in items if i.id in linked)
        plan_out = {
            "annee": plan.annee, "version": plan.version, "missions_prevues": len(items),
            "missions_lancees": started, "missions_cloturees": closed,
            "taux_realisation": round(closed / len(items) * 100, 1) if items else 0.0,
            "budget_jours": sum(i.budget_jours for i in items),
        }  # fmt: skip
    return {
        "filtres": f.describe(),
        "plan": plan_out,
        "missions_par_statut": by_status,
        "budget_jours": budget,
        "jours_consommes": consumed,
        "taux_consommation": round(consumed / budget * 100, 1) if budget else 0.0,
        "missions": [
            {
                "id": str(e.id),
                "reference": e.reference,
                "titre": e.titre,
                "entite": e.entity.nom if e.entity else None,
                "statut": e.statut,
                "budget_jours": e.budget_jours,
                "jours_consommes": round(used.get(e.id, 0.0), 2),
                "ecart_jours": round(e.budget_jours - used.get(e.id, 0.0), 2),
            }
            for e in rows
        ],  # fmt: skip
    }
