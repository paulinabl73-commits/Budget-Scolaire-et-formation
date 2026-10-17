"""Lignée des tables (DAT-24) et rejeu depuis la source (NF-04).

Chaque table naît d'une opération (`AnalysisOperation`) : import, vue ou analyse, avec ses
paramètres et ses tables d'entrée. La lignée d'une table est le graphe de ses ancêtres. Le
rejeu recalcule toute la chaîne depuis les fichiers sources conservés, sans rien enregistrer,
et compare l'empreinte de chaque table recalculée à celle de la table enregistrée.
"""

import shutil
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.relation import Relation, extend
from app.analytics.store import data_dir, file_sha256, parquet_ref, schema_of, write_frame
from app.models.data import AnalysisOperation, Dataset, DatasetKind


def record_operation(
    db: Session,
    ds: Dataset,
    type_: str,
    parametres: dict[str, Any],
    entrees: list[str],
    duree_ms: int | None = None,
) -> AnalysisOperation:
    op = AnalysisOperation(
        engagement_id=ds.engagement_id,
        type=type_,
        parametres=parametres,
        entrees=entrees,
        sortie_id=ds.id,
        statut=ds.statut,
        duree_ms=duree_ms,
        empreinte=ds.parquet_sha256,
    )
    db.add(op)
    return op


def last_operation(db: Session, dataset_id: uuid.UUID) -> AnalysisOperation | None:
    return db.scalar(
        select(AnalysisOperation)
        .where(AnalysisOperation.sortie_id == dataset_id, AnalysisOperation.deleted_at.is_(None))
        .order_by(AnalysisOperation.created_at.desc(), AnalysisOperation.id.desc())
        .limit(1)
    )


def inputs_of(db: Session, ds: Dataset) -> list[str]:
    op = last_operation(db, ds.id)
    if op is not None:
        return list(op.entrees)
    if ds.parent_dataset_id:  # pragma: no cover - tables antérieures à la reprise 0025
        return [str(ds.parent_dataset_id)]
    return []


def lineage(db: Session, ds: Dataset) -> dict[str, Any]:
    """Graphe des ancêtres : nœuds (tables et leur opération) et arêtes entrée → sortie."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    stack = [ds]
    while stack:
        current = stack.pop()
        key = str(current.id)
        if key in nodes:
            continue
        op = last_operation(db, current.id)
        nodes[key] = {
            "id": key,
            "nom": current.nom,
            "kind": current.kind,
            "operation": op.type if op else current.operation or current.kind,
            "parametres": op.parametres if op else {},
            "statut": current.statut,
            "nb_lignes": current.nb_lignes,
            "empreinte": current.parquet_sha256,
            "source_sha256": current.source_sha256,
            "source_nom": current.source_nom,
            "duree_ms": op.duree_ms if op else current.duree_ms,
            "created_at": current.created_at.isoformat() if current.created_at else None,
            "created_by": str(current.created_by) if current.created_by else None,
        }
        for parent_id in inputs_of(db, current):
            edges.append({"de": parent_id, "vers": key})
            parent = db.get(Dataset, uuid.UUID(parent_id))
            if parent is not None:
                stack.append(parent)
    # Profondeur depuis les sources, pour l'affichage en colonnes.
    depth: dict[str, int] = {}

    def level(node_id: str) -> int:
        if node_id not in depth:
            parents = [e["de"] for e in edges if e["vers"] == node_id and e["de"] in nodes]
            depth[node_id] = 1 + max((level(p) for p in parents), default=-1)
        return depth[node_id]

    for node_id in nodes:
        nodes[node_id]["niveau"] = level(node_id)
    ordered = sorted(nodes.values(), key=lambda n: (n["niveau"], n["created_at"] or "", n["id"]))
    unique_edges = sorted({(e["de"], e["vers"]) for e in edges})
    return {"noeuds": ordered, "aretes": [{"de": a, "vers": b} for a, b in unique_edges]}


# --- Rejeu (NF-04) ----------------------------------------------------------------------------


@dataclass
class Replay:
    workdir: str
    etapes: list[dict[str, Any]] = field(default_factory=list)
    cache: dict[str, Relation] = field(default_factory=dict)


def _write(replay: Replay, df: Any) -> tuple[str, str]:
    relative = f"{replay.workdir}/{uuid.uuid4()}.parquet"
    write_frame(df, relative)
    return relative, file_sha256(relative)


def _rebuild(db: Session, ds: Dataset, replay: Replay) -> Relation:
    from app.analytics.jobs import load_dataframe
    from app.analytics.operations import REGISTRY

    key = str(ds.id)
    if key in replay.cache:
        return replay.cache[key]
    step: dict[str, Any] = {"id": key, "nom": ds.nom, "kind": ds.kind, "attendu": ds.parquet_sha256}
    if ds.kind == DatasetKind.IMPORT.value:
        df, _ = load_dataframe(db, ds)
        relative, sha = _write(replay, df)
        rel = Relation(f"SELECT * FROM {parquet_ref(relative)}", [], schema_of(df))  # noqa: S608
    elif ds.kind == DatasetKind.VUE.value:
        parent = db.get(Dataset, ds.parent_dataset_id)
        rel = extend(_rebuild(db, parent, replay), ds.definition.get("champs", []))
        sha = None
    else:
        inputs = [_rebuild(db, db.get(Dataset, uuid.UUID(i)), replay) for i in inputs_of(db, ds)]
        result = REGISTRY[ds.operation].run(inputs, ds.definition["parametres"])
        relative, sha = _write(replay, result.df)
        rel = Relation(f"SELECT * FROM {parquet_ref(relative)}", [], schema_of(result.df))  # noqa: S608
    step["obtenu"] = sha
    step["identique"] = None if sha is None else sha == ds.parquet_sha256
    replay.etapes.append(step)
    replay.cache[key] = rel
    return rel


def replay(db: Session, ds: Dataset) -> dict[str, Any]:
    """Recalcule la table depuis ses sources ; les fichiers recalculés sont ensuite supprimés."""
    run = Replay(workdir=f"_rejeu/{uuid.uuid4()}")
    try:
        _rebuild(db, ds, run)
    finally:
        shutil.rmtree(data_dir() / run.workdir, ignore_errors=True)
    compared = [s for s in run.etapes if s["identique"] is not None]
    return {
        "identique": all(s["identique"] for s in compared),
        "etapes": run.etapes,
    }
