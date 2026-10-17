import io
import time
import uuid

import pytest

from app.config import get_settings
from app.storage import LocalStorage, S3Storage, TooLarge
from tests.test_workpapers import create, ctx  # noqa: F401

PDF = b"%PDF-1.7\n" + b"x" * 2048
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def upload(client, wp, acc, name="facture.pdf", data=PDF):
    return client.post(
        f"/api/workpapers/{wp['id']}/attachments",
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
        headers=acc.headers,
    )


def test_aud15_depot_et_telechargement(client, ctx):  # noqa: F811
    wp = create(client, ctx)
    resp = upload(client, wp, ctx["aud"])
    assert resp.status_code == 201
    a = resp.json()
    assert (a["nom_fichier"], a["taille"], a["version"]) == ("facture.pdf", len(PDF), 1)
    import hashlib

    assert a["sha256"] == hashlib.sha256(PDF).hexdigest()

    # Téléchargement authentifié, puis par lien signé (sans en-tête, pour les balises <img>).
    resp = client.get(f"/api/attachments/{a['id']}/content", headers=ctx["da"].headers)
    assert resp.status_code == 200 and resp.content == PDF
    assert resp.headers["x-content-sha256"] == a["sha256"]
    assert resp.headers["content-disposition"].startswith("inline")
    assert client.get(a["url"]).content == PDF
    assert client.get(f"/api/attachments/{a['id']}/content").status_code == 401
    forged = a["url"].replace("sig=", "sig=0")
    assert client.get(forged).status_code == 401

    # Un même nom forme une nouvelle version ; l'ancienne reste disponible.
    v2 = upload(client, wp, ctx["aud"], data=PDF + b"v2").json()
    assert v2["version"] == 2
    listed = client.get(
        f"/api/workpapers/{wp['id']}/attachments", headers=ctx["aud"].headers
    ).json()
    assert [x["version"] for x in listed] == [2, 1]

    assert (
        client.delete(f"/api/attachments/{a['id']}", headers=ctx["da"].headers).status_code == 403
    )
    assert (
        client.delete(f"/api/attachments/{a['id']}", headers=ctx["aud"].headers).status_code == 204
    )
    assert (
        client.get(f"/api/attachments/{a['id']}/content", headers=ctx["aud"].headers).status_code
        == 404
    )


def test_aud15_controles(client, ctx):  # noqa: F811
    wp = create(client, ctx)
    assert upload(client, wp, ctx["aud"], "script.exe", b"MZ").status_code == 415
    assert upload(client, wp, ctx["aud"], "faux.pdf", b"PK\x03\x04").status_code == 415
    assert upload(client, wp, ctx["aud"], "image.png", PNG).status_code == 201
    assert upload(client, wp, ctx["aud"], "notes.csv", b"a;b\n1;2").status_code == 201
    assert upload(client, wp, ctx["da"]).status_code == 403
    settings = get_settings()
    old = settings.max_upload_mb
    settings.max_upload_mb = 0
    try:
        assert upload(client, wp, ctx["aud"]).status_code == 413
    finally:
        settings.max_upload_mb = old
    assert (
        client.delete(f"/api/attachments/{uuid.uuid4()}", headers=ctx["aud"].headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/attachments/{uuid.uuid4()}/content", headers=ctx["aud"].headers
        ).status_code
        == 404
    )


def test_lien_signe_expire():
    from app.signing import sign, verify

    expires, sig = sign("attachment:x", ttl_seconds=-1)
    assert not verify("attachment:x", expires, sig)
    expires, sig = sign("attachment:x")
    assert verify("attachment:x", expires, sig) and not verify("attachment:y", expires, sig)
    assert expires > time.time()


def test_stockage_local(tmp_path):
    storage = LocalStorage(str(tmp_path))
    stored = storage.put("a/b.bin", io.BytesIO(b"abc"))
    assert stored.size == 3 and storage.exists("a/b.bin")
    assert b"".join(storage.open("a/b.bin")) == b"abc"
    with pytest.raises(FileExistsError):
        storage.put("a/b.bin", io.BytesIO(b"x"))  # jamais de réécriture
    with pytest.raises(TooLarge):
        storage.put("a/c.bin", io.BytesIO(b"abcd"), max_bytes=3)
    assert not storage.exists("a/c.bin")
    with pytest.raises(ValueError):
        storage.put("../evasion", io.BytesIO(b"x"))


class FakeS3:
    def __init__(self):
        self.buckets, self.objects = [], {}

    def list_buckets(self):
        return {"Buckets": [{"Name": b} for b in self.buckets]}

    def create_bucket(self, Bucket):  # noqa: N803
        self.buckets.append(Bucket)

    def upload_fileobj(self, f, bucket, key, ExtraArgs):  # noqa: N803
        assert ExtraArgs["ServerSideEncryption"] == "AES256"
        self.objects[key] = f.read()

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise KeyError(Key)


def test_stockage_s3():
    fake = FakeS3()
    storage = S3Storage(fake, "auditlab")
    assert fake.buckets == ["auditlab"]
    stored = storage.put("k", io.BytesIO(b"contenu"))
    assert stored.size == 7 and storage.exists("k") and not storage.exists("absent")
    assert b"".join(storage.open("k")) == b"contenu"
    S3Storage(fake, "auditlab")  # le bucket existant est réutilisé
    assert fake.buckets == ["auditlab"]
