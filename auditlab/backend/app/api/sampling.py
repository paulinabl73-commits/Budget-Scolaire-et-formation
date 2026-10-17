"""Échantillonnage : calcul de taille (DAT-21) et évaluation MUS (DAT-23)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.sampling import (
    Misstatement,
    SamplingError,
    attribute_sample_size,
    evaluate_mus,
    expansion_factor,
    mus_sample_size,
    poisson_factor,
)
from app.analytics.store import absolute
from app.api.datasets import get_dataset, require_analyst
from app.api.deps import CurrentUser, DbSession
from app.models.data import Dataset, SampleEvaluation
from app.models.engagement import Engagement
from app.models.user import User
from app.security.roles import Perm, has_permission

router = APIRouter(tags=["Échantillonnage"])


class SizeIn(BaseModel):
    type: str = Field(pattern="^(attributs|mus)$")
    confiance: Decimal = Field(ge=Decimal("0.5"), le=Decimal("0.999"))
    # Attributs (tests de contrôles) : taux entre 0 et 1.
    taux_tolerable: Decimal | None = Field(default=None, gt=0, lt=1)
    taux_attendu: Decimal = Field(default=Decimal(0), ge=0, lt=1)
    # MUS (contrôles substantifs) : montants.
    population: Decimal | None = Field(default=None, gt=0)
    erreur_tolerable: Decimal | None = Field(default=None, gt=0)
    erreur_attendue: Decimal = Field(default=Decimal(0), ge=0)


class SizeOut(BaseModel):
    taille: int
    facteur_confiance: float
    facteur_expansion: Decimal | None = None
    intervalle: Decimal | None = None
    methode: str


@router.post("/sampling/size", response_model=SizeOut)
def sample_size(body: SizeIn, user: CurrentUser) -> SizeOut:
    """DAT-21 : taille selon la confiance, l'erreur tolérable et l'erreur attendue."""
    if not has_permission(user.role, Perm.DATA_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    try:
        if body.type == "attributs":
            if body.taux_tolerable is None:
                raise SamplingError("Taux tolérable obligatoire")
            n = attribute_sample_size(
                float(body.confiance), float(body.taux_tolerable), float(body.taux_attendu)
            )
            return SizeOut(
                taille=n,
                facteur_confiance=round(poisson_factor(0, float(body.confiance)), 4),
                methode="Loi binomiale : plus petite taille dont la limite supérieure du taux "
                "d'écart, avec ⌈n × taux attendu⌉ écarts, reste sous le taux tolérable",
            )
        if body.population is None or body.erreur_tolerable is None:
            raise SamplingError("Montant de la population et erreur tolérable obligatoires")
        n = mus_sample_size(
            body.population, body.confiance, body.erreur_tolerable, body.erreur_attendue
        )
        return SizeOut(
            taille=n,
            facteur_confiance=round(poisson_factor(0, float(body.confiance)), 4),
            facteur_expansion=expansion_factor(body.confiance),
            intervalle=(body.population / n).quantize(Decimal("0.01")),
            methode="n = population × facteur de confiance / (erreur tolérable − erreur "
            "attendue × facteur d'expansion)",
        )
    except SamplingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


class ErrorIn(BaseModel):
    ligne: int = Field(ge=1)
    montant_audite: Decimal
    commentaire: str | None = Field(default=None, max_length=2000)


class EvaluationIn(BaseModel):
    confiance: Decimal = Field(default=Decimal("0.95"), ge=Decimal("0.5"), le=Decimal("0.999"))
    erreur_tolerable: Decimal | None = Field(default=None, gt=0)
    erreurs: list[ErrorIn] = Field(default=[], max_length=10_000)


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    confiance: str
    erreur_tolerable: str | None
    erreurs: list[dict[str, Any]]
    resultat: dict[str, Any]
    created_at: datetime | None = None


def _mus_sample(db: Session, dataset_id: uuid.UUID, user: User) -> tuple[Dataset, Engagement]:
    ds, engagement = get_dataset(db, dataset_id, user)
    params = ds.definition.get("parametres", {})
    if ds.operation != "echantillon" or params.get("methode") != "mus" or ds.statut != "pret":
        raise HTTPException(status.HTTP_409_CONFLICT, "Réservé aux échantillons MUS prêts")
    return ds, engagement


@router.post(
    "/datasets/{dataset_id}/mus-evaluations",
    response_model=EvaluationOut,
    status_code=status.HTTP_201_CREATED,
)
def evaluate(
    dataset_id: uuid.UUID, body: EvaluationIn, user: CurrentUser, db: DbSession
) -> SampleEvaluation:
    """DAT-23 : projette les erreurs constatées sur la population (limite supérieure)."""
    import polars as pl

    ds, engagement = _mus_sample(db, dataset_id, user)
    require_analyst(engagement, user)
    amount_col = ds.definition["parametres"]["champ_montant"]
    line_col = ds.schema[0]["nom"]  # rang dans la population, première colonne
    df = pl.read_parquet(absolute(ds.chemin_parquet), columns=[line_col, amount_col])
    book = {int(r): Decimal(str(a)) if a is not None else Decimal(0) for r, a in df.iter_rows()}
    seen: set[int] = set()
    errors: list[Misstatement] = []
    stored = []
    for e in body.erreurs:
        if e.ligne not in book:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"La ligne {e.ligne} n'est pas dans l'échantillon",
            )
        if e.ligne in seen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Ligne {e.ligne} en double")
        seen.add(e.ligne)
        errors.append(Misstatement(e.ligne, book[e.ligne], e.montant_audite))
        stored.append(
            {
                "ligne": e.ligne,
                "montant_comptable": str(book[e.ligne]),
                "montant_audite": str(e.montant_audite),
                "ecart": str(book[e.ligne] - e.montant_audite),
                "commentaire": e.commentaire,
            }
        )
    result = evaluate_mus(
        errors, Decimal(ds.resultat["intervalle"]), float(body.confiance), body.erreur_tolerable
    )
    result["population"] = ds.resultat.get("montant_population")
    result["taille_echantillon"] = ds.resultat.get("taille_echantillon")
    evaluation = SampleEvaluation(
        engagement_id=engagement.id,
        dataset_id=ds.id,
        confiance=str(body.confiance),
        erreur_tolerable=str(body.erreur_tolerable) if body.erreur_tolerable else None,
        erreurs=stored,
        resultat=result,
    )
    db.add(evaluation)
    db.commit()
    return evaluation


@router.get("/datasets/{dataset_id}/mus-evaluations", response_model=list[EvaluationOut])
def list_evaluations(
    dataset_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[SampleEvaluation]:
    ds, _ = _mus_sample(db, dataset_id, user)
    return list(
        db.scalars(
            select(SampleEvaluation)
            .where(SampleEvaluation.dataset_id == ds.id, SampleEvaluation.deleted_at.is_(None))
            .order_by(SampleEvaluation.created_at.desc())
        )
    )
