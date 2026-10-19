"""Journalisation automatique des objets métier (NF-01) et suppression logique (NF-03).

Un écouteur before_flush transforme chaque création, modification ou suppression logique
d'un objet TrackedMixin en entrée AuditLog, dans la même transaction que la modification.
L'auteur est lu dans session.info["actor_id"], posé par l'API après authentification.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.audit.chain import build_entry, seal_pending
from app.models.audit_log import AuditLog
from app.models.base import TrackedMixin

MASK = "***"
_SKIPPED = {"created_at", "updated_at", "created_by", "updated_by"}


class AuditIntegrityError(Exception):
    pass


def set_actor(session: Session, user_id: uuid.UUID | None) -> None:
    session.info["actor_id"] = user_id


def record_event(
    session: Session,
    action: str,
    *,
    object_type: str | None = None,
    object_id: Any = None,
    details: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Journalise un événement qui n'est pas une modification d'objet (connexion, vérification…)."""
    actor = user_id if user_id is not None else session.info.get("actor_id")
    session.add(
        build_entry(
            action=action,
            user_id=actor,
            object_type=object_type,
            object_id=object_id,
            apres=details,
        )
    )


def _value(obj: TrackedMixin, key: str, value: Any) -> Any:
    if key in obj.__audit_masked__ and value is not None:
        return MASK
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, date):  # couvre aussi datetime
        return value.isoformat()
    return value


def _snapshot(obj: TrackedMixin) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    return {
        attr.key: _value(obj, attr.key, getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in _SKIPPED
    }


def _changes(obj: TrackedMixin) -> tuple[dict[str, Any], dict[str, Any]]:
    state = inspect(obj)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        if attr.key in _SKIPPED:
            continue
        hist = state.attrs[attr.key].history
        if not hist.has_changes():
            continue
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        if old == new:
            continue
        before[attr.key] = _value(obj, attr.key, old)
        after[attr.key] = _value(obj, attr.key, new)
    return before, after


@event.listens_for(Session, "before_flush")
def _audit_before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    actor = session.info.get("actor_id")

    for obj in session.deleted:
        if isinstance(obj, TrackedMixin | AuditLog):
            raise AuditIntegrityError(
                f"Suppression physique interdite pour {type(obj).__name__} (NF-03)"
            )

    for obj in list(session.new):
        if isinstance(obj, TrackedMixin):
            if obj.id is None:
                obj.id = uuid.uuid4()
            obj.created_by = obj.created_by or actor
            obj.updated_by = obj.updated_by or actor
            session.add(
                build_entry(
                    action="create",
                    user_id=actor,
                    object_type=type(obj).__name__,
                    object_id=obj.id,
                    apres=_snapshot(obj),
                )
            )

    for obj in list(session.dirty):
        if isinstance(obj, AuditLog) and session.is_modified(obj):
            raise AuditIntegrityError("Le journal d'audit est en ajout seul (NF-02)")
        if not isinstance(obj, TrackedMixin) or not session.is_modified(obj):
            continue
        before, after = _changes(obj)
        if not after:
            continue
        action = "update"
        if "deleted_at" in after:
            action = "delete" if after["deleted_at"] is not None else "restore"
        obj.updated_by = actor
        session.add(
            build_entry(
                action=action,
                user_id=actor,
                object_type=type(obj).__name__,
                object_id=obj.id,
                avant=before,
                apres=after,
            )
        )

    _refuse_closed_engagements(session)

    pending = [o for o in session.new if isinstance(o, AuditLog) and o.hash is None]
    pending.sort(key=lambda e: e.horodatage)
    seal_pending(session, pending)


# NF-08 : seule exception au verrou des missions clôturées, la purge des données après leur
# durée de conservation ne touche que ces colonnes (le contenu purgé est hors base).
PURGE_COLUMNS = {"statut", "purge_le", "sortie", "updated_at", "updated_by"}


def _purge_only(obj: TrackedMixin) -> bool:
    state = inspect(obj)
    changed = {a.key for a in state.mapper.column_attrs if state.attrs[a.key].history.has_changes()}
    return not state.pending and changed <= PURGE_COLUMNS


def _refuse_closed_engagements(session: Session) -> None:
    """AUD-22 : aucune écriture sur un objet rattaché à une mission clôturée.

    Filet de sécurité commun à toutes les routes : la mission elle-même peut changer de statut
    (c'est la clôture), mais rien de ce qui lui est rattaché ne peut plus être créé ou modifié.
    """
    purge = session.info.get("purge_conservation", False)
    ids = {
        getattr(obj, "engagement_id", None)
        for obj in list(session.new) + list(session.dirty)
        if isinstance(obj, TrackedMixin)
        and session.is_modified(obj)
        and not (purge and _purge_only(obj))
    }
    ids.discard(None)
    if not ids:
        return
    from sqlalchemy import select

    from app.models.engagement import Engagement

    closed = (
        session.execute(
            select(Engagement.reference)
            .where(Engagement.id.in_(ids), Engagement.statut == "cloturee")
            .execution_options(autoflush=False)
        )
        .scalars()
        .first()
    )
    if closed:
        raise AuditIntegrityError(f"Mission {closed} clôturée : consultation uniquement")
