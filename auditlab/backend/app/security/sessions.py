"""Sessions serveur à jeton opaque ; seul le SHA-256 du jeton est stocké."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User, UserSession


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def open_session(db: Session, user: User, *, mfa_enrollment_only: bool = False) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        UserSession(
            token_hash=_hash_token(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            mfa_enrollment_only=mfa_enrollment_only,
        )
    )
    return token


def resolve_session(db: Session, token: str) -> UserSession | None:
    """Renvoie la session active et prolonge sa durée de vie, ou None si expirée (NF-07)."""
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
    if sess is None or sess.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    if now - sess.last_seen_at > idle:
        sess.revoked_at = now
        db.commit()
        return None
    sess.last_seen_at = now
    db.commit()
    return sess


def revoke_session(db: Session, sess: UserSession) -> None:
    sess.revoked_at = datetime.now(UTC)


def revoke_all(db: Session, user: User) -> None:
    now = datetime.now(UTC)
    for sess in db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ):
        sess.revoked_at = now
