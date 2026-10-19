"""Exécution d'un script d'analyse (DAT-26) hors du processus de l'application.

1. Préparation : répertoire de travail neuf contenant le code, les tables d'entrée exportées
   en Parquet et les fichiers déposés choisis, décrits par `manifest.json`.
2. Exécution : `bootstrap.py` dans un processus séparé, environnement vidé (aucun secret de
   l'application), durée bornée ; l'isolement (réseau, mémoire) est assuré par l'exécuteur.
3. Reprise : chaque table enregistrée par `audit.save` devient une table de la mission, avec
   sa lignée (script, empreinte du code, entrées) ; indicateurs et sortie console conservés.
"""

import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy.orm import Session

from app.analytics.lineage import record_operation
from app.analytics.relation import RelationError, relation
from app.analytics.store import connect, control_totals, data_dir, file_sha256, write_table
from app.config import get_settings
from app.models.data import Dataset, DatasetKind, DatasetStatus, ScriptRun, Upload
from app.storage import copy_to, get_storage

HERE = Path(__file__).resolve().parent


class ScriptInputError(ValueError):
    """Entrée indisponible (table supprimée ou en erreur, fichier retiré)."""


@dataclass
class Completed:
    returncode: int
    output: str
    timed_out: bool = False


def sha256_text(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:80] or "entree"


def prepare(db: Session, run: ScriptRun, work: Path) -> None:
    (work / "in").mkdir(parents=True)
    (work / "script.py").write_text(run.code, "utf-8")
    manifest: dict[str, dict[str, str]] = {"tables": {}, "fichiers": {}}
    for i, entry in enumerate(run.entrees):
        if entry["type"] == "table":
            ds = db.get(Dataset, uuid.UUID(entry["id"]))
            if ds is None or ds.deleted_at is not None:
                raise ScriptInputError("Table d'entrée supprimée")
            try:
                rel = relation(db, ds)
            except RelationError as exc:
                raise ScriptInputError(f"Table « {ds.nom} » : {exc}") from exc
            target = work / "in" / f"t{i}.parquet"
            path = str(target).replace("'", "''")
            with connect() as con:
                con.execute(f"COPY ({rel.sql}) TO '{path}' (FORMAT parquet)", rel.params)
            manifest["tables"][ds.nom] = f"in/t{i}.parquet"
        else:
            upload = db.get(Upload, uuid.UUID(entry["id"]))
            if upload is None or upload.deleted_at is not None:
                raise ScriptInputError("Fichier d'entrée supprimé")
            relative = f"in/f{i}_{_safe(upload.nom_fichier)}"
            copy_to(get_storage(), upload.storage_key, work / relative)
            manifest["fichiers"][upload.nom_fichier] = relative
    (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")


def execute_local(work: Path, timeout: int) -> Completed:
    """Processus Python séparé, sans les variables d'environnement de l'application."""
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(work), "LANG": "C.UTF-8",
           "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}  # fmt: skip
    try:
        proc = subprocess.run(  # noqa: S603 (commande fixe)
            [sys.executable, "-I", str(HERE / "bootstrap.py"), str(work)],
            cwd=work, env=env, capture_output=True, timeout=timeout, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"") + (exc.stderr or b"")
        return Completed(-1, out.decode("utf-8", errors="replace"), timed_out=True)
    return Completed(proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace"))


def execute(work: Path) -> Completed:
    return execute_local(work, get_settings().scripts_timeout_s)


def _truncate(text: str) -> str:
    limit = get_settings().scripts_output_kb * 1024
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… sortie tronquée"


def _collect(db: Session, run: ScriptRun, work: Path, script_name: str) -> None:
    result = json.loads((work / "out" / "result.json").read_text("utf-8"))
    run.indicateurs = result.get("indicateurs", {})
    inputs = [e["id"] for e in run.entrees if e["type"] == "table"]
    created = []
    for out in result.get("tables", []):
        df = pl.read_parquet(work / out["fichier"])
        written = write_table(df, run.engagement_id)
        ds = Dataset(
            engagement_id=run.engagement_id,
            nom=str(out["nom"])[:200],
            description=f"Produite par le script « {script_name} »",
            kind=DatasetKind.SCRIPT.value,
            statut=DatasetStatus.PRET.value,
            operation="script",
            chemin_parquet=written.chemin,
            nb_lignes=written.nb_lignes,
            nb_colonnes=written.nb_colonnes,
            schema=written.schema,
            totaux_controle=control_totals(written.chemin, written.schema),
            parquet_sha256=file_sha256(written.chemin),
            definition={
                "script_id": str(run.script_id),
                "execution_id": str(run.id),
                "code_sha256": run.code_sha256,
                "entrees": inputs,
            },  # fmt: skip
            created_by=run.created_by,
        )
        db.add(ds)
        db.flush()
        params = {"script": str(run.script_id), "execution": str(run.id),
                  "code_sha256": run.code_sha256}  # fmt: skip
        record_operation(db, ds, "script", params, inputs, run.duree_ms)
        created.append(str(ds.id))
    run.tables = created


def run_script(db: Session, run: ScriptRun, script_name: str) -> None:
    """Exécute l'exécution « en cours » et enregistre son résultat ou son erreur."""
    work = data_dir() / "_scripts" / str(run.id)
    run.debut = dt.datetime.now(dt.UTC)
    start = time.perf_counter()
    try:
        prepare(db, run, work)
        done = execute(work)
        run.duree_ms = int((time.perf_counter() - start) * 1000)
        run.sortie = _truncate(done.output)
        error_file = work / "out" / "erreur.txt"
        if done.timed_out:
            limit = get_settings().scripts_timeout_s
            run.statut, run.erreur = "erreur", f"Durée maximale dépassée ({limit} s)"
        elif error_file.exists():
            run.statut, run.erreur = "erreur", error_file.read_text("utf-8")
        elif done.returncode != 0 or not (work / "out" / "result.json").exists():
            run.statut = "erreur"
            run.erreur = f"Exécution interrompue (code {done.returncode}) : mémoire ou ressources"
        else:
            _collect(db, run, work, script_name)
            run.statut, run.erreur = "termine", None
    except ScriptInputError as exc:
        run.statut, run.erreur = "erreur", str(exc)
    except Exception as exc:  # noqa: BLE001
        run.statut, run.erreur = "erreur", f"Erreur inattendue : {exc}"
    finally:
        run.duree_ms = int((time.perf_counter() - start) * 1000)
        shutil.rmtree(work, ignore_errors=True)


def inputs_out(db: Session, entrees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in entrees:
        obj = db.get(Dataset if e["type"] == "table" else Upload, uuid.UUID(e["id"]))
        nom = None if obj is None else (obj.nom if e["type"] == "table" else obj.nom_fichier)
        out.append({**e, "nom": nom})
    return out
