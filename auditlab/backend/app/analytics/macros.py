"""Macros (DAT-25) : convertir l'historique d'une table en traitement réutilisable.

Les sources de la lignée deviennent les entrées de la macro (avec leurs colonnes et types) ;
les vues et analyses deviennent des étapes rejouées dans l'ordre. Exécuter la macro sur de
nouvelles tables « de même structure » (mêmes colonnes et mêmes types, colonnes en plus
admises) recrée la même chaîne dans la mission de ces tables.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.lineage import inputs_of, lineage, record_operation
from app.analytics.relation import RelationError, extend, relation
from app.models.data import Dataset, DatasetKind, DatasetStatus, Macro


class MacroError(ValueError):
    pass


def build_macro(db: Session, ds: Dataset, nom: str, description: str | None) -> Macro:
    graph = lineage(db, ds)
    refs: dict[str, str] = {}
    entrees: list[dict[str, Any]] = []
    etapes: list[dict[str, Any]] = []
    for node in graph["noeuds"]:
        current = db.get(Dataset, uuid.UUID(node["id"]))
        if current.kind == DatasetKind.IMPORT.value:
            refs[node["id"]] = f"source:{len(entrees)}"
            entrees.append(
                {
                    "nom": current.nom,
                    "colonnes": [{"nom": c["nom"], "type": c["type"]} for c in current.schema],
                }
            )
            continue
        if current.kind == DatasetKind.SCRIPT.value:
            raise MacroError(
                f"« {current.nom} » est produite par un script : réexécutez le script (DAT-26)"
            )
        parents = inputs_of(db, current)
        step: dict[str, Any] = {
            "nom": current.nom,
            "kind": current.kind,
            "entrees": [refs[p] for p in parents],
        }
        if current.kind == DatasetKind.VUE.value:
            step["champs"] = current.definition.get("champs", [])
        else:
            step["operation"] = current.operation
            step["parametres"] = current.definition.get("parametres", {})
        refs[node["id"]] = f"etape:{len(etapes)}"
        etapes.append(step)
    if not etapes:
        raise MacroError("Cette table n'a subi aucune opération : rien à convertir en macro")
    return Macro(
        nom=nom, description=description, entrees=entrees, etapes=etapes, origine_dataset_id=ds.id
    )


def check_structure(spec: dict[str, Any], ds: Dataset) -> None:
    types = {c["nom"]: c["type"] for c in ds.schema}
    for col in spec["colonnes"]:
        if col["nom"] not in types:
            raise MacroError(f"« {ds.nom} » : colonne « {col['nom']} » absente")
        if types[col["nom"]] != col["type"]:
            raise MacroError(
                f"« {ds.nom} » : la colonne « {col['nom']} » est de type {types[col['nom']]}, "
                f"{col['type']} attendu"
            )


def plan_run(db: Session, macro: Macro, inputs: list[Dataset], suffix: str) -> list[Dataset]:
    """Crée les tables de la nouvelle chaîne (en cours) ; la tâche run_macro les calcule."""
    if len(inputs) != len(macro.entrees):
        raise MacroError(f"{len(macro.entrees)} table(s) d'entrée attendue(s)")
    engagement_ids = {d.engagement_id for d in inputs}
    if len(engagement_ids) != 1:
        raise MacroError("Les tables d'entrée doivent appartenir à la même mission")
    for spec, ds in zip(macro.entrees, inputs, strict=True):
        if ds.statut != DatasetStatus.PRET.value:
            raise MacroError(f"« {ds.nom} » n'est pas prête")
        check_structure(spec, ds)
    engagement_id = engagement_ids.pop()
    created: list[Dataset] = []

    def resolve(ref: str) -> Dataset:
        kind, index = ref.split(":")
        return inputs[int(index)] if kind == "source" else created[int(index)]

    for step in macro.etapes:
        parents = [resolve(r) for r in step["entrees"]]
        ds = Dataset(
            engagement_id=engagement_id,
            nom=f"{step['nom']} {suffix}".strip()[:200],
            kind=step["kind"],
            statut=DatasetStatus.EN_COURS.value,
            parent_dataset_id=parents[0].id,
        )
        if step["kind"] == DatasetKind.VUE.value:
            ds.definition = {"champs": step["champs"]}
        else:
            ds.operation = step["operation"]
            ds.definition = {
                "operation": step["operation"],
                "parametres": step["parametres"],
                "entrees": [str(p.id) for p in parents],
                "macro_id": str(macro.id),
            }
        db.add(ds)
        db.flush()
        created.append(ds)
    return created


def build_view(db: Session, view: Dataset) -> None:
    """Calcule le schéma d'une vue créée par une macro."""
    parent = db.get(Dataset, view.parent_dataset_id)
    try:
        rel = extend(relation(db, parent), view.definition.get("champs", []))
    except (RelationError, ValueError) as exc:
        view.statut, view.erreur = DatasetStatus.ERREUR.value, str(exc)
    else:
        view.schema, view.nb_colonnes = rel.schema, len(rel.schema)
        view.nb_lignes = parent.nb_lignes
        view.statut, view.erreur = DatasetStatus.PRET.value, None
    record_operation(
        db, view, "vue", {"champs": view.definition.get("champs", [])}, [str(parent.id)]
    )
