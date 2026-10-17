"""Bibliothèque d'analyses (lot 6) : catalogue et lancement."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.analytics.operations import REGISTRY, AnalysisError, validate
from app.analytics.relation import RelationError, relation
from app.api.datasets import dataset_out, get_dataset, require_analyst
from app.api.deps import CurrentUser, DbSession
from app.models.data import Dataset, DatasetKind, DatasetStatus
from app.schemas_data import DatasetOut

router = APIRouter(tags=["Analyses"])


class AnalysisIn(BaseModel):
    operation: str
    nom: str | None = Field(default=None, max_length=200)
    description: str | None = None
    parametres: dict[str, Any] = {}
    seconde_table_id: uuid.UUID | None = None


@router.get("/analyses")
def catalog(user: CurrentUser) -> list[dict[str, Any]]:
    return [op.describe() for op in REGISTRY.values()]


@router.post(
    "/datasets/{dataset_id}/analyses",
    response_model=DatasetOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def launch(dataset_id: uuid.UUID, body: AnalysisIn, user: CurrentUser, db: DbSession) -> DatasetOut:
    """Contrôle les paramètres puis lance l'analyse en tâche de fond."""
    from app.analytics.jobs import run_analysis

    source, engagement = get_dataset(db, dataset_id, user)
    require_analyst(engagement, user)
    op = REGISTRY.get(body.operation)
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analyse inconnue")
    inputs = [source]
    if op.entrees == 2:
        if body.seconde_table_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Seconde table attendue")
        second, second_engagement = get_dataset(db, body.seconde_table_id, user)
        if second_engagement.id != engagement.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "La seconde table doit être de la mission"
            )
        inputs.append(second)
    try:
        params = validate(op, body.parametres, [relation(db, d) for d in inputs])
    except (AnalysisError, RelationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    ds = Dataset(
        engagement_id=engagement.id,
        nom=body.nom or f"{source.nom} — {op.code}",
        description=body.description,
        kind=DatasetKind.ANALYSE.value,
        statut=DatasetStatus.EN_COURS.value,
        parent_dataset_id=source.id,
        operation=op.code,
        definition={
            "operation": op.code,
            "exigence": op.exigence,
            "parametres": params,
            "entrees": [str(d.id) for d in inputs],
        },
    )
    db.add(ds)
    db.commit()
    run_analysis.delay(str(ds.id))
    db.refresh(ds)
    return dataset_out(ds)
