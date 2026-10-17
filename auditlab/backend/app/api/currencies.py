"""Devises et cours de conversion par date (REV-07)."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession, require
from app.models.revision import Currency, ExchangeRate
from app.models.user import User
from app.security.roles import Perm

router = APIRouter(tags=["Devises"])
Reader = Annotated[User, Depends(require(Perm.REVISION_READ, Perm.FRAMEWORKS_MANAGE))]
Manager = Annotated[User, Depends(require(Perm.FRAMEWORKS_MANAGE))]
RateManager = Annotated[User, Depends(require(Perm.REVISION_MANAGE, Perm.FRAMEWORKS_MANAGE))]


class CurrencyIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(pattern="^[A-Z]{3}$")
    libelle: str = Field(min_length=1, max_length=100)
    decimales: int = Field(ge=0, le=4)


class RateIn(BaseModel):
    devise_source: str = Field(pattern="^[A-Z]{3}$")
    devise_cible: str = Field(pattern="^[A-Z]{3}$")
    date: dt.date
    taux: Decimal = Field(gt=0, max_digits=20, decimal_places=10)
    source: str | None = Field(default=None, max_length=200)


class RateOut(RateIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


def active_currencies(db: DbSession) -> list[Currency]:
    return list(
        db.scalars(select(Currency).where(Currency.deleted_at.is_(None)).order_by(Currency.code))
    )


@router.get("/currencies", response_model=list[CurrencyIO])
def list_currencies(user: Reader, db: DbSession) -> list[Currency]:
    return active_currencies(db)


@router.post("/currencies", response_model=CurrencyIO, status_code=status.HTTP_201_CREATED)
def create_currency(body: CurrencyIO, user: Manager, db: DbSession) -> Currency:
    if any(c.code == body.code for c in active_currencies(db)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Devise déjà définie")
    currency = Currency(**body.model_dump())
    db.add(currency)
    db.commit()
    return currency


@router.get("/exchange-rates", response_model=list[RateOut])
def list_rates(
    user: Reader, db: DbSession, devise: str | None = None, limit: int = 200
) -> list[ExchangeRate]:
    query = select(ExchangeRate).where(ExchangeRate.deleted_at.is_(None))
    if devise:
        query = query.where(
            (ExchangeRate.devise_source == devise) | (ExchangeRate.devise_cible == devise)
        )
    query = query.order_by(ExchangeRate.date.desc(), ExchangeRate.devise_source)
    return list(db.scalars(query.limit(min(limit, 1000))))


@router.post("/exchange-rates", response_model=RateOut, status_code=status.HTTP_201_CREATED)
def create_rate(body: RateIn, user: RateManager, db: DbSession) -> ExchangeRate:
    codes = {c.code for c in active_currencies(db)}
    if (
        body.devise_source == body.devise_cible
        or not {body.devise_source, body.devise_cible} <= codes
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Deux devises distinctes et définies attendues"
        )
    duplicate = db.scalar(
        select(ExchangeRate).where(
            ExchangeRate.devise_source == body.devise_source,
            ExchangeRate.devise_cible == body.devise_cible,
            ExchangeRate.date == body.date,
            ExchangeRate.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un cours existe déjà à cette date")
    rate = ExchangeRate(**body.model_dump())
    db.add(rate)
    db.commit()
    return rate


@router.delete("/exchange-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rate(rate_id: uuid.UUID, user: RateManager, db: DbSession) -> None:
    rate = db.get(ExchangeRate, rate_id)
    if rate is None or rate.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cours introuvable")
    rate.deleted_at, rate.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()
