"""Champs calculés (DAT-06) : vues sur une table, sans copie ni modification de la source."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.analytics.expr import FUNCTION_NAMES, ExprError, compile_expression
from app.analytics.relation import Relation, RelationError, evaluate, extend, relation
from app.analytics.store import quote_ident
from app.api.datasets import dataset_out, get_dataset, require_analyst
from app.api.deps import CurrentUser, DbSession
from app.models.data import Dataset, DatasetKind, DatasetStatus
from app.schemas_data import DatasetOut

router = APIRouter(tags=["Données"])


class FieldIn(BaseModel):
    nom: str = Field(min_length=1, max_length=63, pattern=r"^[^\"\[\]]+$")
    expression: str = Field(min_length=1, max_length=4000)


class ViewIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    description: str | None = None
    champs: list[FieldIn] = Field(min_length=1, max_length=50)


class ViewUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    champs: list[FieldIn] = Field(min_length=1, max_length=50)


class ExpressionIn(BaseModel):
    expression: str = Field(min_length=1, max_length=4000)


class ExpressionOut(BaseModel):
    valide: bool
    erreur: str | None = None
    position: int | None = None
    type: str | None = None
    apercu: list[Any] = []
    colonnes: list[str] = []


def _invalid(message: str, position: int | None = None) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, {"message": message, "position": position}
    )


def _build(base: Relation, champs: list[FieldIn]) -> tuple[Relation, dict[str, int]]:
    """Vérifie les noms, compile les champs et compte leurs valeurs vides sur toute la table
    (une erreur de conversion apparaît ainsi dès la création)."""
    existing = {c.lower() for c in base.types}
    for champ in champs:
        if champ.nom.strip().lower() in existing:
            raise _invalid(f"Le nom « {champ.nom} » est déjà utilisé")
        existing.add(champ.nom.strip().lower())
    try:
        rel = extend(base, [{"nom": c.nom.strip(), "expression": c.expression} for c in champs])
        counted = ", ".join(f"count({quote_ident(c.nom.strip())})" for c in champs)
        counts = evaluate(rel, f"SELECT count(*) AS n, {counted} FROM t").row(0)  # noqa: S608
    except ExprError as exc:
        raise _invalid(str(exc), exc.position) from exc
    except RelationError as exc:
        raise _invalid(str(exc)) from exc
    return rel, {c.nom.strip(): counts[0] - counts[i + 1] for i, c in enumerate(champs)}


def _view_base(db: DbSession, ds: Dataset) -> Relation:
    try:
        return relation(db, ds)
    except RelationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/expressions/functions")
def list_functions(user: CurrentUser) -> list[str]:
    return FUNCTION_NAMES


@router.post("/datasets/{dataset_id}/expressions/validate", response_model=ExpressionOut)
def validate_expression(
    dataset_id: uuid.UUID, body: ExpressionIn, user: CurrentUser, db: DbSession
) -> ExpressionOut:
    """Contrôle à la saisie : syntaxe, colonnes, type du résultat et cinq premières valeurs."""
    ds, _ = get_dataset(db, dataset_id, user)
    base = _view_base(db, ds)
    try:
        compiled = compile_expression(body.expression, base.types)
        df = evaluate(base, f"SELECT {compiled.sql} AS v FROM t LIMIT 5", compiled.params)  # noqa: S608
    except ExprError as exc:
        return ExpressionOut(valide=False, erreur=str(exc), position=exc.position)
    except RelationError as exc:
        return ExpressionOut(valide=False, erreur=str(exc))
    from app.analytics.store import dtype_name

    values = [v if isinstance(v, (int, float, bool, str)) or v is None else str(v) for v in df["v"]]
    return ExpressionOut(
        valide=True,
        type=dtype_name(df.schema["v"]),
        apercu=values,
        colonnes=sorted(compiled.colonnes),
    )


@router.post(
    "/datasets/{dataset_id}/views", response_model=DatasetOut, status_code=status.HTTP_201_CREATED
)
def create_view(
    dataset_id: uuid.UUID, body: ViewIn, user: CurrentUser, db: DbSession
) -> DatasetOut:
    parent, engagement = get_dataset(db, dataset_id, user)
    require_analyst(engagement, user)
    rel, vides = _build(_view_base(db, parent), body.champs)
    view = Dataset(
        engagement_id=engagement.id,
        nom=body.nom,
        description=body.description,
        kind=DatasetKind.VUE.value,
        statut=DatasetStatus.PRET.value,
        parent_dataset_id=parent.id,
        nb_lignes=parent.nb_lignes,
        nb_colonnes=len(rel.schema),
        schema=rel.schema,
        definition={"champs": [c.model_dump() for c in body.champs], "valeurs_vides": vides},
    )
    db.add(view)
    db.commit()
    return dataset_out(view)


@router.put("/datasets/{dataset_id}/view", response_model=DatasetOut)
def update_view(
    dataset_id: uuid.UUID, body: ViewUpdate, user: CurrentUser, db: DbSession
) -> DatasetOut:
    """Une vue se modifie librement : elle ne contient aucune donnée."""
    view, engagement = get_dataset(db, dataset_id, user)
    require_analyst(engagement, user)
    if view.kind != DatasetKind.VUE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seule une vue est modifiable")
    parent = db.get(Dataset, view.parent_dataset_id)
    rel, vides = _build(_view_base(db, parent), body.champs)
    if body.nom:
        view.nom = body.nom
    if body.description is not None:
        view.description = body.description
    view.schema = rel.schema
    view.nb_colonnes = len(rel.schema)
    view.definition = {"champs": [c.model_dump() for c in body.champs], "valeurs_vides": vides}
    db.commit()
    return dataset_out(view)


class SortIn(BaseModel):
    colonne: str
    sens: str = Field(default="asc", pattern="^(asc|desc)$")


class GridQueryIn(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    tri: list[SortIn] = Field(default=[], max_length=5)
    filtres: dict[str, dict[str, Any]] = Field(default={})
    recherche: str | None = Field(default=None, max_length=200)
    colonnes: list[str] | None = None
    total: bool = True


class GridPageOut(BaseModel):
    colonnes: list[str]
    lignes: list[list[Any]]
    total: int | None


@router.post("/datasets/{dataset_id}/rows", response_model=GridPageOut)
def read_rows(
    dataset_id: uuid.UUID, body: GridQueryIn, user: CurrentUser, db: DbSession
) -> GridPageOut:
    """DAT-07 : page de lignes pour la grille virtualisée (lecture seule)."""
    from app.analytics.grid import GridError, read_page

    ds, _ = get_dataset(db, dataset_id, user)
    rel = _view_base(db, ds)
    try:
        page = read_page(
            rel,
            offset=body.offset,
            limit=body.limit,
            sort=[s.model_dump() for s in body.tri],
            filters=body.filtres,
            search=body.recherche,
            columns=body.colonnes,
            with_total=body.total,
        )
    except (GridError, RelationError) as exc:
        raise _invalid(str(exc)) from exc
    return GridPageOut(**page)
