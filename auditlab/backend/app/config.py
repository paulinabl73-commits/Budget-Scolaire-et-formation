from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres de l'application, lus depuis l'environnement (préfixe AUDITLAB_)."""

    model_config = SettingsConfigDict(env_prefix="AUDITLAB_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://auditlab:auditlab@localhost:5432/auditlab"
    # NF-07 : expiration après 30 minutes d'inactivité, verrouillage après 5 échecs.
    session_idle_minutes: int = 30
    max_failed_logins: int = 5
    # Paramètres Argon2 (abaissés uniquement dans les tests).
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4
    totp_issuer: str = "AuditLab"
    # Conversion des heures saisies en jours-homme (AUD-08).
    heures_par_jour: float = 8.0
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
