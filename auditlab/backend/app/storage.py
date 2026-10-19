"""Stockage des fichiers : disque local ou service compatible S3 (SeaweedFS sous Docker).

Les objets ne sont jamais réécrits : chaque dépôt reçoit une clé neuve (pièces jointes et
rapports versionnés). L'empreinte SHA-256 et la taille sont calculées pendant la copie.
"""

import hashlib
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Protocol

from app.config import get_settings

CHUNK = 1024 * 1024


class TooLarge(Exception):
    pass


@dataclass
class Stored:
    key: str
    size: int
    sha256: str


class Storage(Protocol):
    def put(self, key: str, data: BinaryIO, max_bytes: int | None = None) -> Stored: ...

    def open(self, key: str) -> Iterator[bytes]: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


def _copy_hashing(src: BinaryIO, dst: BinaryIO, max_bytes: int | None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := src.read(CHUNK):
        size += len(chunk)
        if max_bytes is not None and size > max_bytes:
            raise TooLarge
        digest.update(chunk)
        dst.write(chunk)
    return size, digest.hexdigest()


class LocalStorage:
    def __init__(self, base: str) -> None:
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.base / key).resolve()
        if self.base.resolve() not in path.parents:
            raise ValueError("Clé de stockage invalide")
        return path

    def put(self, key: str, data: BinaryIO, max_bytes: int | None = None) -> Stored:
        path = self._path(key)
        if path.exists():
            raise FileExistsError(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            try:
                size, sha = _copy_hashing(data, tmp, max_bytes)
            except BaseException:
                Path(tmp.name).unlink(missing_ok=True)
                raise
        Path(tmp.name).rename(path)
        path.chmod(0o440)  # lecture seule
        return Stored(key, size, sha)

    def open(self, key: str) -> Iterator[bytes]:
        with self._path(key).open("rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        """Suppression définitive (purge après la durée de conservation, NF-08)."""
        path = self._path(key)
        if path.exists():
            path.chmod(0o640)
            path.unlink()


class S3Storage:
    def __init__(self, client, bucket: str) -> None:  # noqa: ANN001
        self.client = client
        self.bucket = bucket
        existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)

    def put(self, key: str, data: BinaryIO, max_bytes: int | None = None) -> Stored:
        with tempfile.SpooledTemporaryFile(max_size=16 * CHUNK) as tmp:
            size, sha = _copy_hashing(data, tmp, max_bytes)
            tmp.seek(0)
            self.client.upload_fileobj(
                tmp,
                self.bucket,
                key,
                ExtraArgs={"Metadata": {"sha256": sha}, "ServerSideEncryption": "AES256"},
            )
        return Stored(key, size, sha)

    def open(self, key: str) -> Iterator[bytes]:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        while chunk := body.read(CHUNK):
            yield chunk

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:  # noqa: BLE001
            return False
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
        )
        return S3Storage(client, s.s3_bucket)
    return LocalStorage(s.storage_dir)


def copy_to(storage: Storage, key: str, path: str | Path) -> None:
    """Copie un objet stocké vers un fichier local (exports, traitements)."""
    with open(path, "wb") as out:
        for chunk in storage.open(key):
            out.write(chunk)
