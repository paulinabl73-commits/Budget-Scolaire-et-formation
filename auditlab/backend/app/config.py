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
    # Clé de signature des liens de téléchargement ; à fixer en production (32 octets aléatoires).
    secret_key: str = "dev-change-me-" + "0" * 32
    # Stockage des fichiers (AUD-15) : "local" (disque) ou "s3" (SeaweedFS ou autre service compatible S3).
    storage_backend: str = "local"
    storage_dir: str = "/tmp/auditlab-files"  # noqa: S108
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "auditlab"
    max_upload_mb: int = 100
    # Module 2 : fichiers Parquet (disque local rapide), taille maximale des imports,
    # file de tâches (Redis) ; en mode « eager », les tâches s'exécutent dans la requête.
    data_dir: str = "/tmp/auditlab-data"  # noqa: S108
    max_import_mb: int = 2048
    redis_url: str = "redis://localhost:6379/0"
    tasks_eager: bool = True
    duckdb_memory_limit: str = "2GB"
    duckdb_threads: int = 4
    # Envoi des e-mails : sans serveur SMTP, les messages restent en file (journalisés).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool = True
    mail_from: str = "auditlab@localhost"
    public_url: str = "http://localhost:8080"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
