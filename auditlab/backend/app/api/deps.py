"""Contrôle d'accès vérifié côté serveur sur chaque requête (section 2)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit.listeners import set_actor
from app.db import get_db
from app.models.user import User, UserSession
from app.security.roles import Perm, has_permission
from app.security.sessions import resolve_session

DbSession = Annotated[Session, Depends(get_db)]


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    return token


def _session(request: Request, db: DbSession) -> UserSession:
    sess = resolve_session(db, _bearer(request))
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée ou invalide")
    user = sess.user
    if not user.actif or user.deleted_at is not None or user.is_locked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte désactivé ou verrouillé")
    set_actor(db, user.id)
    request.state.user_id = str(user.id)
    return sess


def current_session_any(sess: Annotated[UserSession, Depends(_session)]) -> UserSession:
    """Accepte aussi une session limitée à l'enrôlement TOTP."""
    return sess


def current_session(sess: Annotated[UserSession, Depends(_session)]) -> UserSession:
    if sess.mfa_enrollment_only:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Activez la double authentification pour continuer"
        )
    return sess


def current_user(sess: Annotated[UserSession, Depends(current_session)]) -> User:
    return sess.user


CurrentUser = Annotated[User, Depends(current_user)]


def require(*perms: Perm) -> Callable[..., User]:
    """Exige au moins l'un des droits indiqués."""

    def checker(user: CurrentUser) -> User:
        if not any(has_permission(user.role, p) for p in perms):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
        return user

    return checker


def user_from_request(request: Request, db: Session) -> User:
    """Authentifie une requête hors du mécanisme de dépendances (routes à double accès)."""
    return current_user(current_session(_session(request, db)))
