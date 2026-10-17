from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, require
from app.models.user import Team, User
from app.schemas import TeamIn, TeamOut
from app.security.roles import Perm

router = APIRouter(prefix="/teams", tags=["Équipes"])
Admin = Annotated[User, Depends(require(Perm.USERS_MANAGE))]


@router.get("", response_model=list[TeamOut])
def list_teams(_: CurrentUser, db: DbSession) -> list[Team]:
    return list(
        db.scalars(
            select(Team)
            .where(Team.deleted_at.is_(None))
            .options(selectinload(Team.members))
            .order_by(Team.nom)
        )
    )


@router.post("", response_model=TeamOut, status_code=201)
def create_team(body: TeamIn, _: Admin, db: DbSession) -> Team:
    if db.scalar(select(Team.id).where(Team.nom == body.nom)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Une équipe porte déjà ce nom")
    team = Team(nom=body.nom, description=body.description, members=[])
    db.add(team)
    db.commit()
    return team
