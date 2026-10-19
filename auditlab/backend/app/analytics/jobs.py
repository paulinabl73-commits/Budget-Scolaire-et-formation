"""Tâches longues du Module 2, exécutées par la file de tâches (Celery)."""

import tempfile
import time
import uuid
from pathlib import Path

from app.analytics.formats import ImportFailure, ReadOptions, apply_types, read_source
from app.analytics.lineage import record_operation
from app.analytics.store import control_totals, file_sha256, write_table
from app.audit.listeners import set_actor
from app.db import SessionLocal
from app.models.data import Dataset, DatasetStatus, DataSource, Upload
from app.storage import copy_to, get_storage
from app.tasks import celery


def load_dataframe(db, ds: Dataset, limit: int | None = None):  # noqa: ANN001,ANN201
    """Lit la source d'un import (fichier déposé ou base déclarée) et applique les types."""
    opts_dict = ds.options or {}
    if opts_dict.get("source_id"):
        from app.analytics.sql_source import read_query

        source = db.get(DataSource, uuid.UUID(opts_dict["source_id"]))
        if source is None or not source.actif:
            raise ImportFailure("Source de données inconnue ou désactivée")
        return read_query(source.url, opts_dict["requete"], limit), {}
    upload = db.get(Upload, uuid.UUID(opts_dict["upload_id"]))
    opts = ReadOptions.from_dict({**opts_dict.get("lecture", {}), "limite": limit})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"source{Path(upload.nom_fichier).suffix.lower()}"
        copy_to(get_storage(), upload.storage_key, path)
        df = read_source(path, opts)
    types = {c.nom: c.type for c in opts.colonnes if c.type}
    converted = apply_types(df, types, opts)
    return converted.df, converted.avertissements


@celery.task(name="auditlab.import_dataset")
def import_dataset(dataset_id: str) -> str:
    """Importe la source dans une table Parquet neuve ; l'erreur éventuelle est conservée."""
    start = time.perf_counter()
    with SessionLocal() as db:
        ds = db.get(Dataset, uuid.UUID(dataset_id))
        set_actor(db, ds.created_by)
        try:
            df, warnings = load_dataframe(db, ds)
            written = write_table(df, ds.engagement_id)
        except ImportFailure as exc:
            ds.statut, ds.erreur = DatasetStatus.ERREUR.value, str(exc)
        except Exception as exc:  # noqa: BLE001 (toute erreur est remontée à l'utilisateur)
            ds.statut, ds.erreur = DatasetStatus.ERREUR.value, f"Erreur inattendue : {exc}"
        else:
            ds.chemin_parquet = written.chemin
            ds.nb_lignes, ds.nb_colonnes = written.nb_lignes, written.nb_colonnes
            ds.schema = written.schema
            ds.options = {**ds.options, "avertissements": warnings}
            ds.totaux_controle = control_totals(written.chemin, written.schema)
            ds.parquet_sha256 = file_sha256(written.chemin)
            ds.statut, ds.erreur = DatasetStatus.PRET.value, None
        ds.duree_ms = int((time.perf_counter() - start) * 1000)
        record_operation(db, ds, "import", ds.options, [], ds.duree_ms)
        db.commit()
        return ds.statut


def input_relations(db, ds: Dataset):  # noqa: ANN001,ANN201
    from app.analytics.relation import relation

    ids = ds.definition.get("entrees", [])
    return [relation(db, db.get(Dataset, uuid.UUID(i))) for i in ids]


def execute_analysis(db, ds: Dataset) -> None:  # noqa: ANN001
    """Exécute l'analyse d'une table « en cours » et enregistre son résultat ou son erreur."""
    from app.analytics.operations import REGISTRY, AnalysisError, validate
    from app.analytics.relation import RelationError

    start = time.perf_counter()
    try:
        op = REGISTRY[ds.operation]
        inputs = input_relations(db, ds)
        params = validate(op, ds.definition["parametres"], inputs)
        ds.definition = {**ds.definition, "parametres": params}
        result = op.run(inputs, params)
        written = write_table(result.df, ds.engagement_id)
    except (AnalysisError, RelationError) as exc:
        ds.statut, ds.erreur = DatasetStatus.ERREUR.value, str(exc)
    except Exception as exc:  # noqa: BLE001
        ds.statut, ds.erreur = DatasetStatus.ERREUR.value, f"Erreur inattendue : {exc}"
    else:
        ds.chemin_parquet = written.chemin
        ds.nb_lignes, ds.nb_colonnes = written.nb_lignes, written.nb_colonnes
        ds.schema = written.schema
        ds.resultat = result.resultat
        ds.totaux_controle = control_totals(written.chemin, written.schema)
        ds.parquet_sha256 = file_sha256(written.chemin)
        ds.statut, ds.erreur = DatasetStatus.PRET.value, None
    ds.duree_ms = int((time.perf_counter() - start) * 1000)
    record_operation(
        db, ds, ds.operation, ds.definition["parametres"], ds.definition["entrees"], ds.duree_ms
    )


@celery.task(name="auditlab.run_analysis")
def run_analysis(dataset_id: str) -> str:
    """Exécute une analyse et écrit sa table de résultat (lot 6)."""
    with SessionLocal() as db:
        ds = db.get(Dataset, uuid.UUID(dataset_id))
        set_actor(db, ds.created_by)
        execute_analysis(db, ds)
        db.commit()
        return ds.statut


@celery.task(name="auditlab.run_macro")
def run_macro(dataset_ids: list[str]) -> list[str]:
    """Exécute dans l'ordre les étapes d'une macro (DAT-25) ; une étape en erreur arrête la
    suite, dont les tables passent en erreur."""
    from app.analytics.macros import build_view

    statuses: list[str] = []
    with SessionLocal() as db:
        failed: str | None = None
        for dataset_id in dataset_ids:
            ds = db.get(Dataset, uuid.UUID(dataset_id))
            set_actor(db, ds.created_by)
            if failed:
                ds.statut, ds.erreur = (
                    DatasetStatus.ERREUR.value,
                    f"Étape précédente en erreur : {failed}",
                )
            elif ds.kind == "vue":
                build_view(db, ds)
            else:
                execute_analysis(db, ds)
            if ds.statut == DatasetStatus.ERREUR.value and not failed:
                failed = ds.nom
            db.commit()
            statuses.append(ds.statut)
    return statuses


@celery.task(name="auditlab.run_script")
def run_script(run_id: str) -> str:
    """Exécute un script d'analyse (DAT-26) et reprend ses tables et indicateurs."""
    from app.models.data import Script, ScriptRun
    from app.scripting.runner import run_script as execute

    with SessionLocal() as db:
        run = db.get(ScriptRun, uuid.UUID(run_id))
        set_actor(db, run.created_by)
        execute(db, run, db.get(Script, run.script_id).nom)
        from app.scripting.schedule import after_run

        after_run(db, run)  # DAT-29 : alerte d'une exécution planifiée
        db.commit()
        return run.statut
