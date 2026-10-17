import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.security.roles import Role

# Validation volontairement souple : les annuaires internes utilisent souvent des domaines
# réservés (.local, .lan) que les validateurs stricts refusent.
Email = Annotated[
    str,
    Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    AfterValidator(str.lower),
]


class LoginIn(BaseModel):
    email: Email
    password: str
    totp_code: str | None = None


class LoginOut(BaseModel):
    token: str
    mfa_enrollment_required: bool = False


class MfaSetupOut(BaseModel):
    secret: str
    provisioning_uri: str


class MfaCodeIn(BaseModel):
    code: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nom: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    nom: str
    role: Role
    actif: bool
    mfa_enabled: bool
    is_locked: bool
    teams: list[TeamRef] = []
    created_at: datetime | None = None


class MeOut(UserOut):
    permissions: list[str]
    mfa_required: bool


class UserCreate(BaseModel):
    email: Email
    nom: str = Field(min_length=1, max_length=200)
    role: Role
    password: str
    team_ids: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    actif: bool | None = None
    team_ids: list[uuid.UUID] | None = None


class TeamIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    description: str | None = None


class MemberRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nom: str
    role: Role


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nom: str
    description: str | None
    members: list[MemberRef] = []


class RoleOut(BaseModel):
    code: Role
    libelle: str
    permissions: list[str]
    mfa_obligatoire: bool


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    horodatage: datetime
    user_id: uuid.UUID | None
    user_nom: str | None = None
    action: str
    object_type: str | None
    object_id: str | None
    avant: dict[str, Any] | None
    apres: dict[str, Any] | None
    hash_precedent: str
    hash: str


class AuditLogPage(BaseModel):
    total: int
    items: list[AuditLogOut]


class ChainReportOut(BaseModel):
    ok: bool
    entries: int
    first_broken_seq: int | None
    reason: str | None
