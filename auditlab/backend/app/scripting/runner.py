"""Exécution d'un script d'analyse (DAT-26) hors du processus de l'application.

1. Préparation : répertoire de travail neuf contenant le code, les tables d'entrée exportées
   en Parquet et les fichiers déposés choisis, décrits par `manifest.json`.
2. Exécution isolée (DAT-27) : `bootstrap.py` sans réseau, mémoire et durée bornées,
   environnement vidé (aucun secret de l'application) ; dans un conteneur Docker jetable en
   exploitation, dans un processus local isolé (espace de noms réseau vide, limites du
   noyau) en développement.
3. Reprise : chaque table enregistrée par `audit.save` devient une table de la mission, avec
   sa lignée (script, empreinte du code, entrées) ; indicateurs et sortie console conservés.
"""

import datetime as dt
import hashlib
import json
import os
import shutil
import signal
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


class SandboxUnavailable(RuntimeError):
    """Bac à sable non disponible : le script n'est pas exécuté (jamais sans isolement)."""


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


ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0",
       "PYTHONDONTWRITEBYTECODE": "1"}  # fmt: skip


def work_root() -> Path:
    s = get_settings()
    return Path(s.scripts_work_dir) if s.scripts_work_dir else data_dir() / "_scripts"


def _limits(memory_mb: int, cpu_s: int, max_file_mb: int):  # noqa: ANN202
    """Limites du noyau appliquées au processus du script avant son lancement (mode local)."""

    def apply() -> None:
        import resource

        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()  # groupe de processus propre : tout est arrêté à l'expiration

    return apply


def local_command(work: Path) -> list[str]:
    """Espace de noms réseau vide (aucune interface) : le script n'a pas de réseau."""
    unshare = shutil.which("unshare")
    if unshare is None:
        raise SandboxUnavailable("Bac à sable indisponible : commande unshare absente")
    return [unshare, "--user", "--map-root-user", "--net", "--",
            sys.executable, "-I", str(HERE / "bootstrap.py"), str(work)]  # fmt: skip


def docker_command(work: Path, name: str) -> list[str]:
    """Conteneur jetable : sans réseau, mémoire et processus bornés, racine en lecture seule,
    utilisateur sans privilège ; seul `out/` est accessible en écriture."""
    s = get_settings()
    host = str(work)
    if s.scripts_work_host_dir:
        host = host.replace(str(work_root()), s.scripts_work_host_dir.rstrip("/"), 1)
    cmd = ["docker", "run", "--rm", "--name", name, "--network", "none",
           "--memory", f"{s.scripts_memory_mb}m", "--memory-swap", f"{s.scripts_memory_mb}m",
           "--cpus", str(s.scripts_cpus), "--pids-limit", "256", "--read-only",
           "--tmpfs", "/tmp:size=256m",  # noqa: S108 (tmpfs du conteneur)
           "--user", "65534:65534", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--env", "HOME=/tmp",
           "-v", f"{host}:/work:ro", "-v", f"{host}/out:/work/out:rw",
           "--workdir", "/work"]  # fmt: skip
    if s.scripts_docker_runtime:
        cmd += ["--runtime", s.scripts_docker_runtime]
    return [*cmd, s.scripts_docker_image, "python", "-I", s.scripts_bootstrap_path, "/work"]


def _run(cmd: list[str], work: Path, timeout: int, **kw: Any) -> Completed:
    proc = subprocess.Popen(  # noqa: S603 (commande construite ici, sans interpréteur)
        cmd, cwd=work, env={**ENV, "HOME": str(work)}, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, **kw,
    )  # fmt: skip
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if kw.get("preexec_fn"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        out, _ = proc.communicate()
        return Completed(-1, out.decode("utf-8", errors="replace"), timed_out=True)
    return Completed(proc.returncode, out.decode("utf-8", errors="replace"))


def execute(work: Path) -> Completed:
    s = get_settings()
    if s.scripts_sandbox == "docker":
        (work / "out").mkdir(exist_ok=True)
        os.chmod(work / "out", 0o777)  # noqa: S103 (écrit par l'utilisateur sans privilège)
        name = f"auditlab-script-{work.name}"
        done = _run(docker_command(work, name), work, s.scripts_timeout_s)
        if done.timed_out:
            kill = ["docker", "kill", name]
            subprocess.run(kill, capture_output=True, check=False)  # noqa: S603, S607
        return done
    if s.scripts_sandbox != "local":
        raise SandboxUnavailable(f"Bac à sable inconnu : {s.scripts_sandbox}")
    limits = _limits(s.scripts_memory_mb, s.scripts_timeout_s + 5, s.max_import_mb)
    return _run(local_command(work), work, s.scripts_timeout_s, preexec_fn=limits)


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
    work = work_root() / str(run.id)
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
        elif done.returncode in (137, -signal.SIGKILL, -signal.SIGXCPU):
            limit = get_settings().scripts_memory_mb
            run.statut = "erreur"
            run.erreur = f"Exécution arrêtée : mémoire ({limit} Mo) ou temps de calcul dépassé"
        elif done.returncode != 0 or not (work / "out" / "result.json").exists():
            run.statut = "erreur"
            run.erreur = f"Exécution interrompue (code {done.returncode})"
        else:
            _collect(db, run, work, script_name)
            run.statut, run.erreur = "termine", None
    except (ScriptInputError, SandboxUnavailable) as exc:
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
