"""Tableaux de bord (REP-04 à REP-06), filtres par période, entité et criticité (REP-08)."""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, require
from app.api.mission_access import get_engagement
from app.models.user import User
from app.reporting import dashboards
from app.reporting.dashboards import Filters
from app.security.roles import Perm

router = APIRouter(prefix="/dashboards", tags=["Tableaux de bord"])
Direction = Annotated[User, Depends(require(Perm.DASHBOARDS_GLOBAL))]


def filters(
    debut: dt.date | None = None,
    fin: dt.date | None = None,
    entity_id: uuid.UUID | None = None,
    criticite: str | None = Query(None, pattern="^(faible|moyenne|elevee|critique)$"),
) -> Filters:
    if debut and fin and fin < debut:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Période incohérente")
    return Filters(debut, fin, entity_id, criticite)


Filtered = Annotated[Filters, Depends(filters)]


@router.get("/direction")
def direction(user: Direction, db: DbSession, f: Filtered) -> dict[str, Any]:
    return dashboards.direction(db, user, f)


@router.get("/recommendations")
def recommendations(user: Direction, db: DbSession, f: Filtered) -> dict[str, Any]:
    return dashboards.recommendations(db, user, f)


@router.get("/missions/{engagement_id}")
def mission(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Tableau de bord d'une mission : son équipe et la Direction (missions visibles)."""
    return dashboards.mission(db, get_engagement(db, engagement_id, user))
