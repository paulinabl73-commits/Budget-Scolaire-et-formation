from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, current_session, current_session_any
from app.audit.listeners import record_event, set_actor
from app.config import get_settings
from app.models.user import User, UserSession
from app.schemas import LoginIn, LoginOut, MeOut, MfaCodeIn, MfaSetupOut, PasswordChangeIn
from app.security import totp
from app.security.passwords import (
    DUMMY_HASH,
    check_password_policy,
    hash_password,
    verify_password,
)
from app.security.roles import MFA_REQUIRED, ROLE_PERMISSIONS, Role
from app.security.sessions import open_session, revoke_all, revoke_session

router = APIRouter(prefix="/auth", tags=["Authentification"])

INVALID = "Identifiant ou mot de passe incorrect"


def _register_failure(db: DbSession, user: User, reason: str) -> None:
    user.failed_logins += 1
    details = {"motif": reason, "echecs": user.failed_logins}
    if user.failed_logins >= get_settings().max_failed_logins and user.locked_at is None:
        user.locked_at = datetime.now(UTC)
        details["verrouille"] = True
    record_event(db, "login_failed", object_type="User", object_id=user.id, details=details)
    db.commit()


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: DbSession) -> LoginOut:
    set_actor(db, None)
    user = db.scalar(
        select(User).where(func.lower(User.email) == body.email.lower(), User.deleted_at.is_(None))
    )
    if user is None:
        verify_password(DUMMY_HASH, body.password)
        record_event(db, "login_failed", details={"email": body.email, "motif": "inconnu"})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    if user.is_locked:
        record_event(
            db,
            "login_refused",
            object_type="User",
            object_id=user.id,
            details={"motif": "compte verrouillé"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_423_LOCKED, "Compte verrouillé : contactez un administrateur"
        )
    if not verify_password(user.password_hash, body.password):
        _register_failure(db, user, "mot de passe")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    if not user.actif:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte désactivé")

    enrollment_only = False
    if user.mfa_enabled:
        if not body.totp_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "mfa_required")
        if not totp.verify_code(user.mfa_secret or "", body.totp_code):
            _register_failure(db, user, "code TOTP")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Code de vérification incorrect")
    elif Role(user.role) in MFA_REQUIRED:
        enrollment_only = True

    set_actor(db, user.id)
    if user.failed_logins:
        user.failed_logins = 0
    token = open_session(db, user, mfa_enrollment_only=enrollment_only)
    record_event(
        db, "login", object_type="User", object_id=user.id, details={"mfa": user.mfa_enabled}
    )
    db.commit()
    return LoginOut(token=token, mfa_enrollment_required=enrollment_only)


@router.post("/logout", status_code=204)
def logout(sess: Annotated[UserSession, Depends(current_session_any)], db: DbSession) -> None:
    revoke_session(db, sess)
    record_event(db, "logout", object_type="User", object_id=sess.user_id)
    db.commit()


def _me(user: User) -> MeOut:
    out = MeOut.model_validate(
        {
            **{
                k: getattr(user, k)
                for k in (
                    "id",
                    "email",
                    "nom",
                    "role",
                    "actif",
                    "mfa_enabled",
                    "is_locked",
                    "teams",
                    "created_at",
                )
            },
            "permissions": sorted(ROLE_PERMISSIONS[Role(user.role)]),
            "mfa_required": Role(user.role) in MFA_REQUIRED,
        }
    )
    return out


@router.get("/me", response_model=MeOut)
def me(sess: Annotated[UserSession, Depends(current_session_any)]) -> MeOut:
    return _me(sess.user)


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(
    sess: Annotated[UserSession, Depends(current_session_any)], db: DbSession
) -> MfaSetupOut:
    user = sess.user
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Double authentification déjà active")
    # Un secret en attente d'activation est réutilisé : un double appel ne désynchronise pas
    # le QR code affiché et le secret enregistré.
    if not user.mfa_secret:
        user.mfa_secret = totp.new_secret()
        db.commit()
    return MfaSetupOut(
        secret=user.mfa_secret, provisioning_uri=totp.provisioning_uri(user.mfa_secret, user.email)
    )


@router.post("/mfa/activate", response_model=MeOut)
def mfa_activate(
    body: MfaCodeIn, sess: Annotated[UserSession, Depends(current_session_any)], db: DbSession
) -> MeOut:
    user = sess.user
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Double authentification déjà active")
    if not user.mfa_secret or not totp.verify_code(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code de vérification incorrect")
    user.mfa_enabled = True
    sess.mfa_enrollment_only = False
    db.commit()
    return _me(user)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChangeIn,
    user: CurrentUser,
    sess: Annotated[UserSession, Depends(current_session)],
    db: DbSession,
) -> None:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect")
    if errors := check_password_policy(body.new_password):
        raise HTTPException(422, "Mot de passe trop faible : " + ", ".join(errors))
    user.password_hash = hash_password(body.new_password)
    revoke_all(db, user)
    sess.revoked_at = None
    db.commit()
