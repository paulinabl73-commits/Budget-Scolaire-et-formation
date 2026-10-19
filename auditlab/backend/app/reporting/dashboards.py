"""Tableaux de bord (REP-04 à REP-06, REP-08) : calculs à partir des données de gestion.

Recommandations (REP-05) : une recommandation est un constat validé ; son avancement est celui
de ses plans d'action. Taux de mise en œuvre = plans vérifiés par l'audit / plans retenus
(hors risque accepté) ; sur les plans échus, même rapport limité aux échéances passées. Un
plan est en retard quand son échéance est passée et qu'il n'est ni réalisé ni clos ; il est
rattaché à la direction de l'entité auditée (premier ancêtre de type « direction »).

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
from app.models.finding import (
    CRITICALITY_ORDER,
    ActionPlan,
    ActionPlanStatus,
    Finding,
    FindingStatus,
)
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


def _direction_of(
    entity: AuditableEntity | None, entities: dict[uuid.UUID, AuditableEntity]
) -> str:
    """Direction de rattachement : premier ancêtre de type « direction », sinon l'entité."""
    current = entity
    while current is not None:
        if current.type == "direction":
            return current.nom
        current = entities.get(current.parent_id) if current.parent_id else None
    return entity.nom if entity else "Sans entité"


def recommendations(db: Session, user: User, f: Filters) -> dict[str, Any]:
    """REP-05 : recommandations par criticité et par statut de leurs plans, taux de mise en
    œuvre, plans d'action en retard par direction."""
    scope = missions(db, user, f).with_only_columns(Engagement.id)
    query = select(Finding).where(
        Finding.engagement_id.in_(scope),
        Finding.deleted_at.is_(None),
        Finding.statut == FindingStatus.VALIDE.value,
    )
    if f.criticite:
        query = query.where(Finding.criticite == f.criticite)
    findings = {x.id: x for x in db.scalars(query)}
    plans: list[ActionPlan] = []
    engagements: dict[uuid.UUID, Engagement] = {}
    if findings:
        plans = list(
            db.scalars(
                select(ActionPlan).where(
                    ActionPlan.finding_id.in_(list(findings)), ActionPlan.deleted_at.is_(None)
                )
            )
        )
        ids = {x.engagement_id for x in findings.values()}
        engagements = {
            e.id: e for e in db.scalars(select(Engagement).where(Engagement.id.in_(ids)))
        }
    entities = {e.id: e for e in db.scalars(select(AuditableEntity))}

    def direction_of(p: ActionPlan) -> str:
        engagement = engagements[findings[p.finding_id].engagement_id]
        return _direction_of(entities.get(engagement.entity_id), entities)

    levels = [c.value for c in reversed(CRITICALITY_ORDER)]
    matrix = {c: {s.value: 0 for s in ActionPlanStatus} for c in levels}
    for p in plans:
        matrix[findings[p.finding_id].criticite][p.statut] += 1
    today = dt.date.today()
    verified, accepted = ActionPlanStatus.VERIFIE.value, ActionPlanStatus.RISQUE_ACCEPTE.value
    still_open = (ActionPlanStatus.A_LANCER.value, ActionPlanStatus.EN_COURS.value)
    late = sorted(
        (p for p in plans if p.statut in still_open and p.echeance < today),
        key=lambda p: p.echeance,
    )
    retained = [p for p in plans if p.statut != accepted]
    due = [p for p in retained if p.echeance < today]

    def rate(group: list[ActionPlan]) -> float:
        done = sum(1 for p in group if p.statut == verified)
        return round(done / len(group) * 100, 1) if group else 0.0

    by_direction: dict[str, list[ActionPlan]] = {}
    for p in late:
        by_direction.setdefault(direction_of(p), []).append(p)

    def responsable(p: ActionPlan) -> str | None:
        if p.responsable_nom:
            return p.responsable_nom
        return db.get(User, p.responsable_id).nom if p.responsable_id else None

    return {
        "filtres": f.describe(),
        "constats_par_criticite": {
            c: sum(1 for x in findings.values() if x.criticite == c) for c in levels
        },
        "plans_par_criticite_et_statut": matrix,
        "plans": len(plans),
        "taux_mise_en_oeuvre": rate(retained),
        "taux_mise_en_oeuvre_echus": rate(due),
        "retards_par_direction": [
            {
                "direction": name,
                "plans_en_retard": len(group),
                "plus_ancienne_echeance": min(p.echeance for p in group).isoformat(),
            }
            for name, group in sorted(by_direction.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "plans_en_retard": [
            {
                "id": str(p.id),
                "constat": findings[p.finding_id].reference,
                "mission": engagements[findings[p.finding_id].engagement_id].reference,
                "criticite": findings[p.finding_id].criticite,
                "description": p.description,
                "responsable": responsable(p),
                "echeance": p.echeance.isoformat(),
                "jours_de_retard": (today - p.echeance).days,
                "direction": direction_of(p),
            }
            for p in late
        ],
    }
