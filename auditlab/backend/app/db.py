from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()
# NF-09 : pool assez grand pour la charge d'un processus (les connexions ouvertes au-delà sont
# fermées après usage, ce qui coûte une connexion PostgreSQL par requête sous charge).
engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
