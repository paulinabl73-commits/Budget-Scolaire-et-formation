# ruff: noqa: S603, S607 (commandes d'exploitation fixes : pg_dump, psql, age, scripts ops/)
"""NF-12 : sauvegarde chiffrée puis restauration testée (base, fichiers, chaîne d'audit).

Exécute les scripts d'exploitation réels (ops/) contre la base de test : nécessite pg_dump,
pg_restore, psql et age, sinon le test est ignoré.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.audit.chain import verify_chain
from app.config import get_settings

OPS = Path(__file__).resolve().parents[2] / "ops"
TOOLS = ("pg_dump", "pg_restore", "psql", "age", "age-keygen")
pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in TOOLS), reason="outils de sauvegarde absents"
)


def _env(url, database: str) -> dict[str, str]:
    return {**os.environ, "PGHOST": url.host or "localhost", "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "", "PGPASSWORD": url.password or "", "PGDATABASE": database}  # fmt: skip


def test_nf12_sauvegarde_et_restauration(client, make_user, tmp_path):
    make_user()  # au moins une entrée de journal à restaurer
    url = make_url(get_settings().database_url)
    source_env = _env(url, url.database)
    restored = f"{url.database}_restauration"
    files = tmp_path / "fichiers"
    (files / "piece").mkdir(parents=True)
    (files / "piece" / "facture.pdf").write_bytes(b"%PDF-1.4 justificatif")
    key = tmp_path / "cle.txt"
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    public = next(line.split()[-1] for line in key.read_text().splitlines() if "public key" in line)
    backups = tmp_path / "sauvegardes"
    run = subprocess.run(
        ["sh", str(OPS / "sauvegarde.sh")], capture_output=True, text=True, check=False,
        env={**source_env, "SAUVEGARDE_DIR": str(backups), "SAUVEGARDE_CLE_PUBLIQUE": public,
             "SAUVEGARDE_SOURCES": str(files)},
    )  # fmt: skip
    assert run.returncode == 0, run.stderr
    [folder] = list(backups.iterdir())
    assert {p.name for p in folder.iterdir()} == {
        "base.dump.age",
        "fichiers.tar.gz.age",
        "SHA256SUMS",
    }
    assert b"facture" not in (folder / "fichiers.tar.gz.age").read_bytes()  # chiffré
    admin = {**source_env, "PGDATABASE": "postgres"}
    subprocess.run(["psql", "-qc", f'DROP DATABASE IF EXISTS "{restored}"'], env=admin, check=True)
    subprocess.run(["psql", "-qc", f'CREATE DATABASE "{restored}"'], env=admin, check=True)
    try:
        target = tmp_path / "restauration"
        run = subprocess.run(
            ["sh", str(OPS / "restauration.sh"), str(folder), str(key), str(target)],
            capture_output=True, text=True, check=False, env=_env(url, restored),
        )  # fmt: skip
        assert run.returncode == 0, run.stderr
        assert (
            target / "fichiers" / "piece" / "facture.pdf"
        ).read_bytes() == b"%PDF-1.4 justificatif"
        engine = create_engine(url.set(database=restored))
        source = create_engine(url)
        try:
            with source.connect() as a, engine.connect() as b:
                for table in ("audit_log", "users", "engagements", "datasets"):
                    query = text(f"SELECT count(*) FROM {table}")  # noqa: S608
                    assert a.execute(query).scalar() == b.execute(query).scalar(), table
            with Session(engine) as db:
                report = verify_chain(db)
            assert report.ok and report.entries > 0
        finally:
            engine.dispose()
            source.dispose()
    finally:
        subprocess.run(
            ["psql", "-qc", f'DROP DATABASE IF EXISTS "{restored}"'], env=admin, check=False
        )
    # Une archive altérée est refusée avant toute restauration.
    with (folder / "base.dump.age").open("ab") as f:
        f.write(b"x")
    run = subprocess.run(["sh", str(OPS / "restauration.sh"), str(folder), str(key)],
                         capture_output=True, text=True, check=False, env=_env(url, restored))  # fmt: skip
    assert run.returncode != 0 and "FAILED" in run.stdout + run.stderr
