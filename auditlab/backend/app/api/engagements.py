"""Missions d'audit (AUD-06, AUD-07)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, require
from app.api.mission_access import (
    can_manage,
    ensure_open,
    get_engagement,
    mission_role,
    require_manager,
    visible_engagements,
)
from app.api.universe import get_entity
from app.models.engagement import Engagement, EngagementMember, MissionRole
from app.models.plan import AuditPlan, PlanItem, PlanStatus
from app.models.user import User
from app.schemas_mission import (
    EngagementIn,
    EngagementOut,
    EngagementSummary,
    EngagementUpdate,
    MemberIn,
    MemberOut,
)
from app.security.roles import Perm, Role

router = APIRouter(prefix="/engagements", tags=["Missions"])
Manager = Annotated[User, Depends(require(Perm.MISSIONS_MANAGE))]

# Rôles applicatifs admis pour chaque rôle dans la mission.
ALLOWED_ROLES: dict[MissionRole, set[Role]] = {
    MissionRole.CHEF: {Role.CHEF_MISSION, Role.DIRECTEUR},
    MissionRole.SUPERVISEUR: {Role.DIRECTEUR, Role.CHEF_MISSION},
    MissionRole.AUDITEUR: {Role.AUDITEUR, Role.CHEF_MISSION},
    MissionRole.DATA_ANALYST: {Role.DATA_ANALYST},
}


def consumed_days(db: DbSession, engagement_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    """Jours consommés par mission ; alimenté par la saisie des temps (AUD-08)."""
    return {}


def summary(e: Engagement, user: User, consumed: float) -> dict:
    chef = next((m.user for m in e.members if m.role_mission == MissionRole.CHEF), None)
    return {
        **{k: getattr(e, k) for k in EngagementSummary.model_fields if hasattr(e, k)},
        "entity_nom": e.entity.nom if e.entity else None,
        "chef_nom": chef.nom if chef else None,
        "mon_role": mission_role(e, user),
        "jours_consommes": consumed,
    }


def engagement_out(db: DbSession, e: Engagement, user: User) -> EngagementOut:
    from app.api.engagement_status import allowed_transitions

    return EngagementOut.model_validate(
        {
            **summary(e, user, consumed_days(db, [e.id]).get(e.id, 0.0)),
            "perimetre": e.perimetre,
            "objectifs": e.objectifs,
            "created_at": e.created_at,
            "membres": [
                MemberOut(
                    user_id=m.user_id,
                    nom=m.user.nom,
                    email=m.user.email,
                    role_mission=m.role_mission,
                )
                for m in sorted(
                    e.members, key=lambda m: (m.role_mission != "chef_mission", m.user.nom)
                )
            ],
            "transitions": allowed_transitions(db, e, user),
            "peut_gerer": can_manage(e, user),
        }
    )


def _validate_team(db: DbSession, members: list[MemberIn]) -> list[MemberIn]:
    if len({m.user_id for m in members}) != len(members):
        raise HTTPException(422, "Un membre figure deux fois dans l'équipe")
    if sum(m.role_mission == MissionRole.CHEF for m in members) != 1:
        raise HTTPException(422, "L'équipe doit compter exactement un chef de mission")
    users = {
        u.id: u
        for u in db.scalars(
            select(User).where(
                User.id.in_([m.user_id for m in members]),
                User.deleted_at.is_(None),
                User.actif.is_(True),
            )
        )
    }
    for m in members:
        user = users.get(m.user_id)
        if user is None:
            raise HTTPException(422, "Membre inconnu ou inactif")
        if Role(user.role) not in ALLOWED_ROLES[m.role_mission]:
            raise HTTPException(
                422, f"{user.nom} ne peut pas tenir le rôle « {m.role_mission.value} »"
            )
    return members


def _next_reference(db: DbSession, year: int) -> str:
    prefix = f"M-{year}-"
    count = db.scalar(
        select(func.count()).select_from(Engagement).where(Engagement.reference.like(prefix + "%"))
    )
    return f"{prefix}{(count or 0) + 1:03d}"


def set_team(db: DbSession, engagement: Engagement, members: list[MemberIn]) -> None:
    from datetime import UTC, datetime

    current = {m.user_id: m for m in engagement.members}
    wanted = {m.user_id: m for m in members}
    for user_id, member in current.items():
        if user_id not in wanted:
            member.deleted_at = datetime.now(UTC)
        elif member.role_mission != wanted[user_id].role_mission:
            member.role_mission = wanted[user_id].role_mission.value
    for user_id, m in wanted.items():
        if user_id not in current:
            db.add(
                EngagementMember(
                    engagement_id=engagement.id, user_id=user_id, role_mission=m.role_mission.value
                )
            )


@router.get("", response_model=list[EngagementSummary])
def list_engagements(user: CurrentUser, db: DbSession, statut: str | None = None) -> list[dict]:
    query = visible_engagements(user).options(
        selectinload(Engagement.members).selectinload(EngagementMember.user),
        selectinload(Engagement.entity),
    )
    if statut:
        query = query.where(Engagement.statut == statut)
    engagements = list(
        db.scalars(query.order_by(Engagement.date_debut.desc(), Engagement.reference))
    )
    consumed = consumed_days(db, [e.id for e in engagements])
    return [summary(e, user, consumed.get(e.id, 0.0)) for e in engagements]


@router.post("", response_model=EngagementOut, status_code=201)
def create_engagement(body: EngagementIn, user: Manager, db: DbSession) -> EngagementOut:
    values: dict = {
        "titre": body.titre,
        "perimetre": body.perimetre,
        "objectifs": body.objectifs,
        "date_debut": body.date_debut,
        "date_fin": body.date_fin,
        "budget_jours": body.budget_jours,
        "entity_id": body.entity_id,
    }
    if body.plan_item_id:
        item = db.scalar(
            select(PlanItem).where(PlanItem.id == body.plan_item_id, PlanItem.deleted_at.is_(None))
        )
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission du plan introuvable")
        plan = db.get(AuditPlan, item.plan_id)
        if plan is None or plan.statut != PlanStatus.VALIDE:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Seul un plan validé peut lancer des missions"
            )
        if db.scalar(
            select(Engagement.id).where(
                Engagement.plan_item_id == item.id, Engagement.deleted_at.is_(None)
            )
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Cette mission du plan est déjà lancée")
        values.update(
            titre=values["titre"] or item.titre,
            date_debut=values["date_debut"] or item.periode_debut,
            date_fin=values["date_fin"] or item.periode_fin,
            budget_jours=values["budget_jours"] or item.budget_jours,
            entity_id=item.entity_id,
            plan_id=plan.id,
            plan_item_id=item.id,
        )
    if values["entity_id"]:
        get_entity(db, values["entity_id"])
    missing = [k for k in ("titre", "date_debut", "date_fin", "budget_jours") if not values[k]]
    if missing:
        raise HTTPException(422, "Champs obligatoires manquants : " + ", ".join(missing))
    if values["date_fin"] < values["date_debut"]:
        raise HTTPException(422, "La date de fin précède la date de début")

    members = list(body.membres)
    if (
        not any(m.role_mission == MissionRole.CHEF for m in members)
        and Role(user.role) in (ALLOWED_ROLES[MissionRole.CHEF])
    ):
        # Le créateur pilote la mission si personne d'autre n'est désigné.
        members = [m for m in members if m.user_id != user.id]
        members.insert(0, MemberIn(user_id=user.id, role_mission=MissionRole.CHEF))
    _validate_team(db, members)

    engagement = Engagement(
        reference=_next_reference(db, values["date_debut"].year), statut="planifiee", **values
    )
    db.add(engagement)
    db.flush()
    for m in members:
        db.add(
            EngagementMember(
                engagement_id=engagement.id, user_id=m.user_id, role_mission=m.role_mission.value
            )
        )
    db.commit()
    return engagement_out(db, get_engagement(db, engagement.id, user), user)


@router.get("/{engagement_id}", response_model=EngagementOut)
def read_engagement(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> EngagementOut:
    return engagement_out(db, get_engagement(db, engagement_id, user), user)


@router.patch("/{engagement_id}", response_model=EngagementOut)
def update_engagement(
    engagement_id: uuid.UUID, body: EngagementUpdate, user: CurrentUser, db: DbSession
) -> EngagementOut:
    engagement = get_engagement(db, engagement_id, user)
    require_manager(engagement, user)
    ensure_open(engagement)
    changes = body.model_dump(exclude_unset=True)
    debut = changes.get("date_debut") or engagement.date_debut
    fin = changes.get("date_fin") or engagement.date_fin
    if fin < debut:
        raise HTTPException(422, "La date de fin précède la date de début")
    for key, value in changes.items():
        if value is not None or key in ("perimetre", "objectifs"):
            setattr(engagement, key, value)
    db.commit()
    return engagement_out(db, get_engagement(db, engagement.id, user), user)


@router.put("/{engagement_id}/members", response_model=EngagementOut)
def replace_team(
    engagement_id: uuid.UUID, members: list[MemberIn], user: CurrentUser, db: DbSession
) -> EngagementOut:
    engagement = get_engagement(db, engagement_id, user)
    require_manager(engagement, user)
    ensure_open(engagement)
    set_team(db, engagement, _validate_team(db, members))
    db.commit()
    return engagement_out(db, get_engagement(db, engagement.id, user), user)


@router.get("/{engagement_id}/candidates", response_model=list[MemberOut])
def candidates(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    """Personnes pouvant rejoindre l'équipe, avec le rôle de mission par défaut."""
    engagement = get_engagement(db, engagement_id, user)
    require_manager(engagement, user)
    return team_candidates(db)


def team_candidates(db: DbSession) -> list[MemberOut]:
    default = {
        Role.CHEF_MISSION: MissionRole.CHEF,
        Role.DIRECTEUR: MissionRole.SUPERVISEUR,
        Role.AUDITEUR: MissionRole.AUDITEUR,
        Role.DATA_ANALYST: MissionRole.DATA_ANALYST,
    }
    users = db.scalars(
        select(User)
        .where(
            User.deleted_at.is_(None),
            User.actif.is_(True),
            User.role.in_([r.value for r in default]),
        )
        .order_by(User.nom)
    )
    return [
        MemberOut(user_id=u.id, nom=u.nom, email=u.email, role_mission=default[Role(u.role)])
        for u in users
    ]


staff_router = APIRouter(prefix="/staff", tags=["Missions"])


@staff_router.get("", response_model=list[MemberOut])
def staff(_: Manager, db: DbSession) -> list[MemberOut]:
    """Personnes pouvant être affectées à une mission (formulaire de création)."""
    return team_candidates(db)
