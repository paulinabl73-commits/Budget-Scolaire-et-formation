"""DAT-30 : joindre une table de résultat, son historique et un graphique à un papier."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.analytics.lineage import lineage
from app.analytics.relation import RelationError, evaluate, relation
from app.analytics.store import quote_ident
from app.api.datasets import get_dataset
from app.api.deps import CurrentUser, DbSession
from app.api.signoffs import invalidate
from app.api.workpapers import get_workpaper, require_preparer
from app.models.data import Dataset
from app.models.workpaper import WorkpaperDataLink

router = APIRouter(tags=["Papiers de travail"])

MAX_POINTS = 30
SNAPSHOT_KEYS = ("id", "nom", "kind", "operation", "parametres", "empreinte", "niveau")


class ChartIn(BaseModel):
    categorie: str = Field(min_length=1, max_length=200)
    valeur: str | None = Field(default=None, max_length=200)  # vide : nombre de lignes
    limite: int = Field(default=15, ge=1, le=MAX_POINTS)


class LinkIn(BaseModel):
    dataset_id: uuid.UUID
    graphique: ChartIn | None = None
    commentaire: str | None = Field(default=None, max_length=4000)


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workpaper_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_nom: str | None = None
    empreinte: str | None
    empreinte_actuelle: str | None = None
    nb_lignes: int | None
    lignee: dict[str, Any]
    graphique: dict[str, Any]
    commentaire: str | None
    created_at: datetime | None = None


def chart_snapshot(db: DbSession, ds: Dataset, spec: ChartIn | None) -> dict[str, Any]:
    """Données du graphique figées au moment du lien."""
    if spec is None:
        if ds.resultat.get("chiffres"):  # Benford : la distribution observée et attendue
            return {"type": "benford", "chiffres": ds.resultat["chiffres"]}
        return {}
    rel = relation(db, ds)
    types = rel.types
    if spec.categorie not in types or (spec.valeur and spec.valeur not in types):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Colonne du graphique inconnue")
    if spec.valeur and types[spec.valeur] not in ("entier", "decimal"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La valeur du graphique doit être numérique"
        )
    cat = quote_ident(spec.categorie)
    measure = f"sum({quote_ident(spec.valeur)})" if spec.valeur else "count(*)"
    df = evaluate(
        rel,
        f"SELECT CAST({cat} AS VARCHAR) AS c, CAST({measure} AS DOUBLE) AS v FROM t "  # noqa: S608
        f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {spec.limite}",
    )
    return {
        "type": "barres",
        "categorie": spec.categorie,
        "valeur": spec.valeur,
        "points": [{"etiquette": c, "valeur": v} for c, v in df.iter_rows()],
    }


def link_out(db: DbSession, link: WorkpaperDataLink) -> LinkOut:
    out = LinkOut.model_validate(link)
    ds = db.get(Dataset, link.dataset_id)
    out.dataset_nom = ds.nom if ds else None
    out.empreinte_actuelle = ds.parquet_sha256 if ds else None
    return out


@router.post(
    "/workpapers/{workpaper_id}/data-links",
    response_model=LinkOut,
    status_code=status.HTTP_201_CREATED,
)
def attach(workpaper_id: uuid.UUID, body: LinkIn, user: CurrentUser, db: DbSession) -> LinkOut:
    wp, engagement = get_workpaper(db, workpaper_id, user)
    require_preparer(engagement, user)
    ds, ds_engagement = get_dataset(db, body.dataset_id, user)
    if ds_engagement.id != engagement.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La table doit appartenir à la même mission"
        )
    if ds.statut != "pret":
        raise HTTPException(status.HTTP_409_CONFLICT, "La table n'est pas prête")
    try:
        chart = chart_snapshot(db, ds, body.graphique)
    except RelationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    graph = lineage(db, ds)
    link = WorkpaperDataLink(
        engagement_id=engagement.id,
        workpaper_id=wp.id,
        dataset_id=ds.id,
        empreinte=ds.parquet_sha256,
        nb_lignes=ds.nb_lignes,
        lignee={
            "noeuds": [
                {
                    k: n[k]
                    for k in ("id", "nom", "kind", "operation", "parametres", "empreinte", "niveau")
                }
                for n in graph["noeuds"]
            ],
            "aretes": graph["aretes"],
        },
        graphique=chart,
        commentaire=body.commentaire,
    )
    db.add(link)
    invalidate(db, wp, engagement, user, f"table « {ds.nom} » jointe")
    db.commit()
    return link_out(db, link)


@router.get("/workpapers/{workpaper_id}/data-links", response_model=list[LinkOut])
def list_links(workpaper_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[LinkOut]:
    wp, _ = get_workpaper(db, workpaper_id, user)
    links = db.scalars(
        select(WorkpaperDataLink)
        .where(WorkpaperDataLink.workpaper_id == wp.id, WorkpaperDataLink.deleted_at.is_(None))
        .order_by(WorkpaperDataLink.created_at)
    )
    return [link_out(db, link) for link in links]


@router.delete("/data-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach(link_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    from datetime import UTC

    link = db.scalar(
        select(WorkpaperDataLink).where(
            WorkpaperDataLink.id == link_id, WorkpaperDataLink.deleted_at.is_(None)
        )
    )
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lien introuvable")
    wp, engagement = get_workpaper(db, link.workpaper_id, user)
    require_preparer(engagement, user)
    link.deleted_at, link.deleted_by = datetime.now(UTC), user.id
    ds = db.get(Dataset, link.dataset_id)
    invalidate(db, wp, engagement, user, f"table « {ds.nom} » retirée")
    db.commit()
