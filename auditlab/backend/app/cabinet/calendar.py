"""Calendrier fiscal et social (RCO-03) : échéances d'un client et alertes avant échéance."""

import calendar
import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.dates import add_months, exercise_end
from app.config import get_settings
from app.models.portfolio import CalendarRule, Client, ClientDeadline
from app.notify import notify

PERIODICITES = ("mensuelle", "trimestrielle", "annuelle", "cloture")


@dataclass(frozen=True)
class Occurrence:
    rule: CalendarRule
    echeance: dt.date
    periode: str


def _day(year: int, month: int, day: int | None) -> dt.date:
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day or last, last))


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def occurrences(
    rule: CalendarRule, client: Client, start: dt.date, end: dt.date
) -> list[Occurrence]:
    """Échéances de la règle comprises entre `start` et `end` inclus."""
    out: list[Occurrence] = []
    if rule.periodicite in ("mensuelle", "trimestrielle"):
        step = 1 if rule.periodicite == "mensuelle" else 3
        year, month = start.year - 1, 1
        while (year, month) <= (end.year, end.month):
            if step == 1 or month % 3 == 0:
                ny, nm = _next_month(year, month)
                label = f"{month:02d}/{year}" if step == 1 else f"T{month // 3} {year}"
                out.append(Occurrence(rule, _day(ny, nm, rule.jour), label))
            year, month = _next_month(year, month)
    elif rule.periodicite == "annuelle":
        for year in range(start.year, end.year + 1):
            out.append(Occurrence(rule, _day(year, rule.mois or 1, rule.jour), str(year)))
    else:  # cloture
        for year in range(start.year - 2, end.year + 1):
            closing = exercise_end(client, year)
            due = add_months(closing, rule.decalage_mois or 0)
            if rule.jour:
                due = _day(due.year, due.month, rule.jour)
            out.append(Occurrence(rule, due, f"exercice {year}"))
    return [o for o in out if start <= o.echeance <= end]


def client_rules(db: Session, client: Client) -> list[CalendarRule]:
    rows = db.scalars(
        select(CalendarRule)
        .where(
            CalendarRule.pays == client.pays,
            CalendarRule.actif.is_(True),
            CalendarRule.deleted_at.is_(None),
        )
        .order_by(CalendarRule.code)
    )
    return [r for r in rows if not r.regimes or client.regime_fiscal in r.regimes]


def tracking(db: Session, client: Client) -> dict[tuple, ClientDeadline]:
    rows = db.scalars(
        select(ClientDeadline).where(
            ClientDeadline.client_id == client.id, ClientDeadline.deleted_at.is_(None)
        )
    )
    return {(r.rule_id, r.echeance): r for r in rows}


def client_deadlines(
    db: Session, client: Client, start: dt.date, end: dt.date, today: dt.date | None = None
) -> list[dict]:
    today = today or dt.date.today()
    done = tracking(db, client)
    items = [o for r in client_rules(db, client) for o in occurrences(r, client, start, end)]
    out = []
    for o in sorted(items, key=lambda x: (x.echeance, x.rule.code)):
        row = done.get((o.rule.id, o.echeance))
        fait = row is not None and row.fait_le is not None
        out.append(
            {
                "rule_id": str(o.rule.id),
                "code": o.rule.code,
                "libelle": o.rule.libelle,
                "nature": o.rule.nature,
                "periode": o.periode,
                "echeance": o.echeance.isoformat(),
                "fait_le": row.fait_le.isoformat() if fait else None,
                "statut": "fait" if fait else "en_retard" if o.echeance < today else "a_venir",
                "jours_restants": (o.echeance - today).days,
            }
        )
    return out


def send_calendar_alerts(db: Session, today: dt.date | None = None) -> int:
    """Alerte l'expert-comptable et le collaborateur à J-15 et J-5 (paramétrable) d'une
    échéance non faite ; une seule alerte par échéance et par délai."""
    today = today or dt.date.today()
    delays = sorted(get_settings().alertes_echeances_jours, reverse=True)
    count = 0
    clients = db.scalars(select(Client).where(Client.deleted_at.is_(None), Client.actif.is_(True)))
    for client in clients:
        done = tracking(db, client)
        horizon = today + dt.timedelta(days=max(delays, default=0))
        for rule in client_rules(db, client):
            for o in occurrences(rule, client, today, horizon):
                left = (o.echeance - today).days
                due = [d for d in delays if left <= d]
                if not due:
                    continue
                row = done.get((rule.id, o.echeance))
                if row is None:
                    row = ClientDeadline(client_id=client.id, rule_id=rule.id, echeance=o.echeance)
                    db.add(row)
                    done[(rule.id, o.echeance)] = row
                # Le délai le plus court atteint, s'il n'a pas déjà donné lieu à une alerte.
                delay = min(due)
                if row.fait_le is not None or delay in (row.alertes or []):
                    continue
                row.alertes = [
                    *(row.alertes or []),
                    *[d for d in due if d not in (row.alertes or [])],
                ]
                notify(
                    db,
                    {client.expert_id, client.collaborateur_id},
                    "echeance",
                    f"{client.raison_sociale} : {rule.libelle} le {o.echeance:%d/%m/%Y}",
                    f"Échéance « {rule.libelle} » ({o.periode}) du dossier {client.raison_sociale} "
                    f"dans {left} jour(s), le {o.echeance:%d/%m/%Y}.",
                    lien=f"/portefeuille/{client.id}",
                )
                count += 1
    db.commit()
    return count
