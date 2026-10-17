"""Liens de téléchargement signés et à durée limitée (images des papiers de travail)."""

import hashlib
import hmac
import time

from app.config import get_settings


def _signature(resource: str, expires: int) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{resource}:{expires}".encode(), hashlib.sha256).hexdigest()


def sign(resource: str, ttl_seconds: int = 3600) -> tuple[int, str]:
    expires = int(time.time()) + ttl_seconds
    return expires, _signature(resource, expires)


def verify(resource: str, expires: int, signature: str) -> bool:
    if expires < time.time():
        return False
    return hmac.compare_digest(_signature(resource, expires), signature)
