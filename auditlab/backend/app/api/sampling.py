"""Échantillonnage : calcul de taille (DAT-21) et évaluation MUS (DAT-23)."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.analytics.sampling import (
    SamplingError,
    attribute_sample_size,
    expansion_factor,
    mus_sample_size,
    poisson_factor,
)
from app.api.deps import CurrentUser
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
