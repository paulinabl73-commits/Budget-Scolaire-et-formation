import os

os.environ.setdefault(
    "AUDITLAB_DATABASE_URL",
    "postgresql+psycopg://auditlab:auditlab@localhost:5432/auditlab_test",
)
# Argon2 allégé pour des tests rapides.
os.environ["AUDITLAB_ARGON2_TIME_COST"] = "1"
os.environ["AUDITLAB_ARGON2_MEMORY_COST"] = "1024"
os.environ["AUDITLAB_ARGON2_PARALLELISM"] = "1"

from collections.abc import Callable, Iterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import pyotp  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.audit.listeners import set_actor  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.security.roles import Role  # noqa: E402

PASSWORD = "MotDePasse-Solide-2026"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    with engine.begin() as conn:
        # Le mode « replica » neutralise le déclencheur d'ajout seul, pour les tests uniquement.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("TRUNCATE audit_log, user_sessions, user_teams, teams, users CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@dataclass
class Account:
    user: User
    headers: dict[str, str]
    totp: pyotp.TOTP | None = None


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def _make(
        role: Role = Role.AUDITEUR, email: str | None = None, mfa: bool | None = None, **kw: object
    ) -> User:
        set_actor(db, None)
        mfa = role in (Role.ADMIN, Role.DIRECTEUR) if mfa is None else mfa
        user = User(
            email=email or f"{role.value}@exemple.org",
            nom=kw.pop("nom", f"Utilisateur {role.value}"),
            role=role.value,
            password_hash=hash_password(PASSWORD),
            actif=True,
            mfa_enabled=mfa,
            mfa_secret=pyotp.random_base32() if mfa else None,
            failed_logins=0,
            **kw,
        )
        db.add(user)
        db.commit()
        return user

    return _make


def login(client: TestClient, user: User) -> dict[str, str]:
    body: dict[str, str] = {"email": user.email, "password": PASSWORD}
    if user.mfa_enabled:
        body["totp_code"] = pyotp.TOTP(user.mfa_secret).now()
    resp = client.post("/api/auth/login", json=body)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def account(client: TestClient, make_user: Callable[..., User]) -> Callable[..., Account]:
    def _account(role: Role = Role.AUDITEUR, **kw: object) -> Account:
        user = make_user(role, **kw)
        return Account(
            user, login(client, user), pyotp.TOTP(user.mfa_secret) if user.mfa_secret else None
        )

    return _account
