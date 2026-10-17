import os

os.environ.setdefault(
    "AUDITLAB_DATABASE_URL",
    "postgresql+psycopg://auditlab:auditlab@localhost:5432/auditlab_test",
)
# Argon2 allégé pour des tests rapides.
os.environ["AUDITLAB_ARGON2_TIME_COST"] = "1"
os.environ["AUDITLAB_ARGON2_MEMORY_COST"] = "1024"
os.environ["AUDITLAB_ARGON2_PARALLELISM"] = "1"
import tempfile  # noqa: E402

os.environ["AUDITLAB_STORAGE_DIR"] = tempfile.mkdtemp(prefix="auditlab-tests-")
os.environ["AUDITLAB_DATA_DIR"] = tempfile.mkdtemp(prefix="auditlab-data-")
os.environ["AUDITLAB_TASKS_EAGER"] = "true"

from collections.abc import Callable, Iterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import pyotp  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.audit.listeners import set_actor  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.security.roles import Role  # noqa: E402

PASSWORD = "MotDePasse-Solide-2026"
BACKEND = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield


def _truncate_all() -> None:
    with engine.begin() as conn:
        # Le mode « replica » neutralise le déclencheur d'ajout seul, pour les tests uniquement.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    # Base vide au départ de chaque test, y compris des données livrées par les migrations.
    _truncate_all()
    yield


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
        if email is None:
            # Adresse par défaut lisible ; suffixée si le rôle a déjà un compte dans le test.
            from sqlalchemy import func, select

            n = db.scalar(select(func.count()).where(User.role == role.value)) or 0
            email = f"{role.value}@exemple.org" if n == 0 else f"{role.value}{n + 1}@exemple.org"
        user = User(
            email=email,
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


DEFAULT_CRITERIA = [
    ("IMPACT_FIN", "Impact financier", "impact", "note", 3.0),
    ("IMPACT_REG", "Impact réglementaire", "impact", "note", 2.0),
    ("PROBA", "Probabilité", "probabilite", "note", 3.0),
    ("CTRL_INT", "Contrôle interne", "probabilite", "note", 2.0),
    ("ANCIENNETE", "Ancienneté", "autre", "anciennete", 1.0),
]


@pytest.fixture
def criteria(db: Session) -> list:
    """Critères par défaut (ceux que la migration 0003 installe)."""
    from app.models import RiskCriterion

    rows = [
        RiskCriterion(code=c, libelle=lib, axe=axe, mode=mode, poids=poids, ordre=i, actif=True)
        for i, (c, lib, axe, mode, poids) in enumerate(DEFAULT_CRITERIA)
    ]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture
def syscohada(db: Session):
    """Référentiel SYSCOHADA livré (la troncature des tests efface les données de départ)."""
    from app.revision.currency import seed_currencies
    from app.revision.frameworks import builtin, load_framework

    fw = load_framework(db, builtin("syscohada_2017"))
    seed_currencies(db)
    db.commit()
    return fw
