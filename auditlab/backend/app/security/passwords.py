from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings


@lru_cache
def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Hash factice : vérifié quand l'utilisateur n'existe pas, pour un temps de réponse constant.
DUMMY_HASH = hash_password("compte-inexistant")


def check_password_policy(password: str) -> list[str]:
    """Règles minimales ; renvoie la liste des manquements (vide si conforme)."""
    errors = []
    if len(password) < 12:
        errors.append("au moins 12 caractères")
    if not any(c.isupper() for c in password):
        errors.append("au moins une majuscule")
    if not any(c.islower() for c in password):
        errors.append("au moins une minuscule")
    if not any(c.isdigit() for c in password):
        errors.append("au moins un chiffre")
    return errors
