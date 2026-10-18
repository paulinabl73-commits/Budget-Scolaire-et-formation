"""Dates d'exercice d'un client du cabinet."""

import calendar
import datetime as dt

from app.models.portfolio import Client


def exercise_end(client: Client, year: int) -> dt.date:
    last = calendar.monthrange(year, client.mois_cloture)[1]
    return dt.date(year, client.mois_cloture, min(client.jour_cloture, last))


def add_months(day: dt.date, months: int) -> dt.date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
