"""Module 6 — portefeuille de dossiers clients (RCO-01) et clôtures par exercice.

Une clôture est une mission en mode « revision_comptable » (expert-comptable chef de mission,
collaborateur auditeur, superviseur facultatif) portant un dossier de révision du Module 5 :
import des balances, affectation et états y sont repris tels quels.
"""

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.audit_files import AuditFileIn, _check_currency, _check_frameworks
from app.api.audit_files import create_file as create_audit_file
from app.api.deps import CurrentUser, DbSession
from app.api.engagements import _next_reference, _validate_team
from app.api.mission_access import sees_all
from app.cabinet.dates import add_months, exercise_end
from app.models.engagement import Engagement, EngagementMember, MissionRole
from app.models.portfolio import Client, Closing
from app.models.revision import AccountingFramework
from app.models.universe import AuditableEntity
from app.models.user import User
from app.notify import notify
from app.schemas_mission import MemberIn
from app.security.roles import Perm, Role, has_permission

router = APIRouter(tags=["Portefeuille (Module 6)"])
MODE = "revision_comptable"
FORMES = ("SA", "SARL", "SAS", "SNC", "SCS", "GIE", "EI", "association", "OPS", "autre")
REGIMES = ("reel_normal", "reel_simplifie", "entreprenant", "exonere", "autre")
TAILLES = ("tpe", "pme", "grande")


class ClientIn(BaseModel):
    raison_sociale: str = Field(min_length=2, max_length=200)
    forme_juridique: Literal[FORMES]  # type: ignore[valid-type]
    regime_fiscal: Literal[REGIMES]  # type: ignore[valid-type]
    framework_id: uuid.UUID
    pays: str = Field(min_length=2, max_length=40)
    devise: str = Field(default="XOF", pattern="^[A-Z]{3}$")
    jour_cloture: int = Field(default=31, ge=1, le=31)
    mois_cloture: int = Field(default=12, ge=1, le=12)
    taille: Literal[TAILLES] = "pme"  # type: ignore[valid-type]
    identifiant_fiscal: str | None = Field(default=None, max_length=50)
    rccm: str | None = Field(default=None, max_length=50)
    expert_id: uuid.UUID | None = None
    collaborateur_id: uuid.UUID | None = None
    superviseur_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    budget_jours: float = Field(default=5, gt=0, le=1000)


class ClientUpdate(BaseModel):
    raison_sociale: str | None = Field(default=None, min_length=2, max_length=200)
    forme_juridique: Literal[FORMES] | None = None  # type: ignore[valid-type]
    regime_fiscal: Literal[REGIMES] | None = None  # type: ignore[valid-type]
    taille: Literal[TAILLES] | None = None  # type: ignore[valid-type]
    identifiant_fiscal: str | None = Field(default=None, max_length=50)
    rccm: str | None = Field(default=None, max_length=50)
    collaborateur_id: uuid.UUID | None = None
    superviseur_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    budget_jours: float | None = Field(default=None, gt=0, le=1000)
    actif: bool | None = None


class ClosingIn(BaseModel):
    exercice: int = Field(ge=1990, le=2100)
    budget_jours: float | None = Field(default=None, gt=0, le=1000)


def visible_clients(user: User) -> Any:
    query = select(Client).where(Client.deleted_at.is_(None))
    if sees_all(user):
        return query
    return query.where(
        or_(
            Client.expert_id == user.id,
            Client.collaborateur_id == user.id,
            Client.superviseur_id == user.id,
        )
    )


def can_manage_client(client: Client, user: User) -> bool:
    return has_permission(user.role, Perm.PORTFOLIO_MANAGE) and (
        sees_all(user) or client.expert_id == user.id
    )


def get_client(db: Session, client_id: uuid.UUID, user: User) -> Client:
    client = db.scalar(visible_clients(user).where(Client.id == client_id))
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier client introuvable")
    return client


def require_client_manager(client: Client, user: User) -> None:
    if not can_manage_client(client, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'expert-comptable du dossier")


def _check_user(db: Session, user_id: uuid.UUID | None, roles: set[Role], label: str) -> None:
    if user_id is None:
        return
    u = db.get(User, user_id)
    if u is None or u.deleted_at is not None or not u.actif or Role(u.role) not in roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label} invalide")


def _check_people(db: Session, data: dict[str, Any]) -> None:
    _check_user(db, data.get("expert_id"), {Role.EXPERT_COMPTABLE}, "Expert-comptable")
    _check_user(db, data.get("collaborateur_id"), {Role.COLLABORATEUR}, "Collaborateur")
    _check_user(
        db,
        data.get("superviseur_id"),
        {Role.EXPERT_COMPTABLE, Role.CHEF_MISSION, Role.DIRECTEUR},
        "Superviseur",
    )
    _check_user(db, data.get("contact_id"), {Role.AUDITE}, "Contact du client")


def client_out(db: Session, c: Client, user: User) -> dict[str, Any]:
    fw = db.get(AccountingFramework, c.framework_id)

    def name(uid: uuid.UUID | None) -> str | None:
        return db.get(User, uid).nom if uid else None

    closings = db.scalars(
        select(Closing)
        .where(Closing.client_id == c.id, Closing.deleted_at.is_(None))
        .order_by(Closing.exercice.desc())
    ).all()
    return {
        **{
            k: getattr(c, k)
            for k in (
                "id",
                "raison_sociale",
                "forme_juridique",
                "regime_fiscal",
                "framework_id",
                "pays",
                "devise",
                "jour_cloture",
                "mois_cloture",
                "taille",
                "identifiant_fiscal",
                "rccm",
                "expert_id",
                "collaborateur_id",
                "superviseur_id",
                "contact_id",
                "budget_jours",
                "actif",
                "entity_id",
            )
        },  # fmt: skip
        "referentiel": f"{fw.code} {fw.version} ({fw.pays})",
        "expert_nom": name(c.expert_id),
        "collaborateur_nom": name(c.collaborateur_id),
        "superviseur_nom": name(c.superviseur_id),
        "contact_nom": name(c.contact_id),
        "date_cloture": f"{c.jour_cloture:02d}/{c.mois_cloture:02d}",
        "clotures": [closing_out(x) for x in closings],
        "peut_gerer": can_manage_client(c, user),
    }


def closing_out(c: Closing) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "exercice": c.exercice,
        "engagement_id": str(c.engagement_id),
        "audit_file_id": str(c.audit_file_id),
        "etape": c.etape,
        "etapes": c.etapes,
        "date_depot": c.date_depot.isoformat() if c.date_depot else None,
    }


@router.get("/clients")
def list_clients(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    if not has_permission(user.role, Perm.REVISION_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    rows = db.scalars(visible_clients(user).order_by(Client.raison_sociale))
    return [client_out(db, c, user) for c in rows]


@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(body: ClientIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if not has_permission(user.role, Perm.PORTFOLIO_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux experts-comptables")
    data = body.model_dump()
    if data["expert_id"] is None:
        if user.role != Role.EXPERT_COMPTABLE:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Expert-comptable du dossier à désigner"
            )
        data["expert_id"] = user.id
    elif not sees_all(user) and data["expert_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Un expert-comptable crée ses dossiers")
    _check_people(db, data)
    _check_frameworks(db, body.framework_id, None)
    _check_currency(db, body.devise)
    entity = AuditableEntity(nom=body.raison_sociale, type="client")
    db.add(entity)
    db.flush()
    client = Client(entity_id=entity.id, **data)
    db.add(client)
    db.commit()
    return client_out(db, client, user)


@router.get("/clients/{client_id}")
def read_client(client_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return client_out(db, get_client(db, client_id, user), user)


@router.patch("/clients/{client_id}")
def update_client(
    client_id: uuid.UUID, body: ClientUpdate, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    client = get_client(db, client_id, user)
    require_client_manager(client, user)
    data = body.model_dump(exclude_unset=True)
    _check_people(db, data)
    for key, value in data.items():
        setattr(client, key, value)
    if "raison_sociale" in data:
        db.get(AuditableEntity, client.entity_id).nom = data["raison_sociale"]
    db.commit()
    return client_out(db, client, user)


@router.post("/clients/{client_id}/closings", status_code=status.HTTP_201_CREATED)
def open_closing(
    client_id: uuid.UUID, body: ClosingIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Ouvre la clôture d'un exercice : mission, équipe du dossier et dossier de révision."""
    client = get_client(db, client_id, user)
    require_client_manager(client, user)
    if not client.actif:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier client inactif")
    exists = db.scalar(
        select(Closing).where(
            Closing.client_id == client.id,
            Closing.exercice == body.exercice,
            Closing.deleted_at.is_(None),
        )
    )
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Clôture déjà ouverte pour cet exercice")
    end = exercise_end(client, body.exercice)
    start = exercise_end(client, body.exercice - 1) + dt.timedelta(days=1)
    members = [MemberIn(user_id=client.expert_id, role_mission=MissionRole.CHEF)]
    if client.collaborateur_id:
        members.append(MemberIn(user_id=client.collaborateur_id, role_mission=MissionRole.AUDITEUR))
    if client.superviseur_id and client.superviseur_id != client.expert_id:
        members.append(
            MemberIn(user_id=client.superviseur_id, role_mission=MissionRole.SUPERVISEUR)
        )
    _validate_team(db, members, MODE)
    engagement = Engagement(
        reference=_next_reference(db, end.year),
        titre=f"Clôture {body.exercice} – {client.raison_sociale}",
        date_debut=end,
        # Comptes arrêtés et approuvés dans les six mois de la clôture (OHADA).
        date_fin=add_months(end, 6),
        budget_jours=body.budget_jours or client.budget_jours,
        entity_id=client.entity_id,
        statut="planifiee",
        mode=MODE,
    )
    db.add(engagement)
    db.flush()
    for m in members:
        db.add(
            EngagementMember(
                engagement_id=engagement.id, user_id=m.user_id, role_mission=m.role_mission.value
            )
        )
    db.flush()
    db.refresh(engagement)
    file = create_audit_file(
        engagement.id,
        AuditFileIn(
            exercice=body.exercice,
            date_debut=start,
            date_fin=end,
            framework_id=client.framework_id,
            devise=client.devise,
            pays=client.pays,
        ),
        user,
        db,
    )
    closing = Closing(
        client_id=client.id,
        exercice=body.exercice,
        engagement_id=engagement.id,
        audit_file_id=file.id,
        etape="pieces",
        etapes={"pieces": dt.date.today().isoformat()},
    )
    db.add(closing)
    # RCO-06 : documents permanents expirés signalés à l'ouverture de l'exercice.
    from app.api.permanent import expired

    stale = expired(db, client, max(dt.date.today(), end))
    if stale:
        notify(
            db,
            {client.expert_id, client.collaborateur_id},
            "documents_expires",
            f"{client.raison_sociale} : {len(stale)} document(s) permanent(s) expiré(s)",
            "Documents à renouveler avant la clôture "
            f"{body.exercice} : "
            + "; ".join(f"{d.libelle} ({d.date_validite:%d/%m/%Y})" for d in stale),
            lien=f"/portefeuille/{client.id}",
        )
    db.commit()
    return {
        **closing_out(closing),
        "documents_expires": [
            {"id": str(d.id), "libelle": d.libelle, "date_validite": d.date_validite.isoformat()}
            for d in stale
        ],
    }


@router.get("/portfolio/staff")
def staff(user: CurrentUser, db: DbSession) -> dict[str, list[dict[str, Any]]]:
    """Personnes pouvant être désignées sur un dossier client."""
    if not has_permission(user.role, Perm.PORTFOLIO_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    groups = {
        "experts": [Role.EXPERT_COMPTABLE],
        "collaborateurs": [Role.COLLABORATEUR],
        "superviseurs": [Role.EXPERT_COMPTABLE, Role.CHEF_MISSION, Role.DIRECTEUR],
        "contacts": [Role.AUDITE],
    }
    out = {}
    for key, roles in groups.items():
        users = db.scalars(
            select(User)
            .where(
                User.deleted_at.is_(None),
                User.actif.is_(True),
                User.role.in_([r.value for r in roles]),
            )
            .order_by(User.nom)
        )
        out[key] = [{"id": str(u.id), "nom": u.nom, "email": u.email} for u in users]
    return out
