from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import CurrentUser, DbSession
from app.schemas import RoleOut
from app.security.roles import MFA_REQUIRED, ROLE_LABELS, ROLE_PERMISSIONS, Role

router = APIRouter(tags=["Général"])


@router.get("/health")
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/roles", response_model=list[RoleOut])
def roles(_: CurrentUser) -> list[RoleOut]:
    return [
        RoleOut(
            code=r,
            libelle=ROLE_LABELS[r],
            permissions=sorted(ROLE_PERMISSIONS[r]),
            mfa_obligatoire=r in MFA_REQUIRED,
        )
        for r in Role
    ]
