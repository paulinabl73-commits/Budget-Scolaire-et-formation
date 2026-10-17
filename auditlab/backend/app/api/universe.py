"""Univers d'audit : entités auditables en arborescence (AUD-01)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select

from app.api.deps import DbSession, require
from app.models.universe import AuditableEntity
from app.models.user import User
from app.schemas_plan import EntityIn, EntityOut, EntityUpdate
from app.security.roles import Perm

router = APIRouter(prefix="/universe", tags=["Univers d'audit"])
Reader = Annotated[User, Depends(require(Perm.PLAN_READ))]
Manager = Annotated[User, Depends(require(Perm.PLAN_MANAGE))]


def active_entities() -> Select[tuple[AuditableEntity]]:
    return select(AuditableEntity).where(AuditableEntity.deleted_at.is_(None))


def get_entity(db: DbSession, entity_id: uuid.UUID) -> AuditableEntity:
    entity = db.scalar(active_entities().where(AuditableEntity.id == entity_id))
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entité introuvable")
    return entity


def _check_parent(db: DbSession, entity_id: uuid.UUID | None, parent_id: uuid.UUID) -> None:
    """Le parent doit exister et ne pas être l'entité elle-même ni l'un de ses descendants."""
    current: uuid.UUID | None = parent_id
    while current is not None:
        if current == entity_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Une entité ne peut pas être rattachée à sa propre branche",
            )
        current = get_entity(db, current).parent_id


@router.get("/entities", response_model=list[EntityOut])
def list_entities(_: Reader, db: DbSession) -> list[AuditableEntity]:
    return list(db.scalars(active_entities().order_by(AuditableEntity.nom)))


@router.post("/entities", response_model=EntityOut, status_code=201)
def create_entity(body: EntityIn, _: Manager, db: DbSession) -> AuditableEntity:
    if body.parent_id:
        _check_parent(db, None, body.parent_id)
    entity = AuditableEntity(**body.model_dump(mode="python"))
    entity.type = body.type.value
    db.add(entity)
    db.commit()
    return entity


@router.get("/entities/{entity_id}", response_model=EntityOut)
def read_entity(entity_id: uuid.UUID, _: Reader, db: DbSession) -> AuditableEntity:
    return get_entity(db, entity_id)


@router.patch("/entities/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: uuid.UUID, body: EntityUpdate, _: Manager, db: DbSession
) -> AuditableEntity:
    entity = get_entity(db, entity_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("parent_id"):
        _check_parent(db, entity.id, changes["parent_id"])
    for key, value in changes.items():
        if key in ("nom", "type") and value is None:
            continue
        setattr(entity, key, value.value if key == "type" else value)
    db.commit()
    return entity


@router.delete("/entities/{entity_id}", status_code=204)
def delete_entity(entity_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    entity = get_entity(db, entity_id)
    if db.scalar(active_entities().where(AuditableEntity.parent_id == entity.id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Supprimez ou déplacez d'abord les entités rattachées"
        )
    entity.deleted_at = datetime.now(UTC)
    entity.deleted_by = user.id
    db.commit()
