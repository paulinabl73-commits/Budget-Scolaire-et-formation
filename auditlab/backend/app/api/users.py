import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require
from app.models.user import Team, User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security.passwords import check_password_policy, hash_password
from app.security.roles import Perm
from app.security.sessions import revoke_all

router = APIRouter(prefix="/users", tags=["Utilisateurs"])
Admin = Annotated[User, Depends(require(Perm.USERS_MANAGE))]


def _get(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    return user


def _teams(db: DbSession, ids: list[uuid.UUID]) -> list[Team]:
    teams = list(db.scalars(select(Team).where(Team.id.in_(ids), Team.deleted_at.is_(None))))
    if len(teams) != len(set(ids)):
        raise HTTPException(422, "Équipe inconnue")
    return teams


@router.get("", response_model=list[UserOut])
def list_users(_: Admin, db: DbSession) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.deleted_at.is_(None))
            .options(selectinload(User.teams))
            .order_by(User.nom)
        )
    )


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _: Admin, db: DbSession) -> User:
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Adresse e-mail déjà utilisée")
    if errors := check_password_policy(body.password):
        raise HTTPException(422, "Mot de passe trop faible : " + ", ".join(errors))
    user = User(
        email=body.email.lower(),
        nom=body.nom,
        role=body.role.value,
        password_hash=hash_password(body.password),
        actif=True,
        mfa_enabled=False,
        failed_logins=0,
        teams=_teams(db, body.team_ids),
    )
    db.add(user)
    db.commit()
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, _: Admin, db: DbSession) -> User:
    return _get(db, user_id)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, admin: Admin, db: DbSession) -> User:
    user = _get(db, user_id)
    if user.id == admin.id and (body.role not in (None, user.role) or body.actif is False):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Vous ne pouvez pas modifier votre propre rôle ou statut"
        )
    if body.nom is not None:
        user.nom = body.nom
    if body.role is not None and body.role != user.role:
        user.role = body.role.value
        # Un nouveau rôle peut imposer la double authentification : on rouvre la session.
        revoke_all(db, user)
    if body.actif is not None:
        user.actif = body.actif
        if not body.actif:
            revoke_all(db, user)
    if body.team_ids is not None:
        user.teams = _teams(db, body.team_ids)
    db.commit()
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: uuid.UUID, admin: Admin, db: DbSession) -> None:
    user = _get(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Vous ne pouvez pas supprimer votre compte")
    user.deleted_at = datetime.now(UTC)
    user.deleted_by = admin.id
    user.actif = False
    revoke_all(db, user)
    db.commit()


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: uuid.UUID, _: Admin, db: DbSession) -> User:
    user = _get(db, user_id)
    user.locked_at = None
    user.failed_logins = 0
    db.commit()
    return user


@router.post("/{user_id}/reset-mfa", response_model=UserOut)
def reset_mfa(user_id: uuid.UUID, _: Admin, db: DbSession) -> User:
    user = _get(db, user_id)
    user.mfa_secret = None
    user.mfa_enabled = False
    revoke_all(db, user)
    db.commit()
    return user
