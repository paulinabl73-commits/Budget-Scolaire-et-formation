"""Jeux de données d'une mission (Module 2)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.store import is_read_only
from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import ensure_open, get_engagement, mission_role, sees_all
from app.models.data import Dataset
from app.models.engagement import Engagement
from app.models.user import User
from app.schemas_data import DatasetOut
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Données"])


def require_read(engagement: Engagement, user: User) -> None:
    if not has_permission(user.role, Perm.DATA_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")


def require_analyst(engagement: Engagement, user: User) -> None:
    """Imports et analyses : membres de la mission ayant le droit d'analyser."""
    ensure_open(engagement)
    if not has_permission(user.role, Perm.DATA_ANALYZE) or (
        mission_role(engagement, user) is None and not sees_all(user)
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux membres de la mission habilités à analyser"
        )


def get_dataset(db: Session, dataset_id: uuid.UUID, user: User) -> tuple[Dataset, Engagement]:
    ds = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.deleted_at.is_(None)))
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table introuvable")
    engagement = get_engagement(db, ds.engagement_id, user)
    require_read(engagement, user)
    return ds, engagement


def dataset_out(ds: Dataset) -> DatasetOut:
    out = DatasetOut.model_validate(ds)
    if ds.chemin_parquet:
        out.lecture_seule = is_read_only(ds.chemin_parquet)
    return out


@router.get("/engagements/{engagement_id}/datasets", response_model=list[DatasetOut])
def list_datasets(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[DatasetOut]:
    engagement = get_engagement(db, engagement_id, user)
    require_read(engagement, user)
    rows = db.scalars(
        select(Dataset)
        .where(Dataset.engagement_id == engagement.id, Dataset.deleted_at.is_(None))
        .order_by(Dataset.created_at)
    )
    return [dataset_out(d) for d in rows]


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def read_dataset(dataset_id: uuid.UUID, user: CurrentUser, db: DbSession) -> DatasetOut:
    ds, _ = get_dataset(db, dataset_id, user)
    return dataset_out(ds)
