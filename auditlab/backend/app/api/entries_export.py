"""Export des écritures générées au format d'import du logiciel du client (RCO-17) : l'outil
ne tient pas la comptabilité, les écritures acceptées sont reprises dans le logiciel."""

import csv
import io
import json
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.api.adjustments import file_adjustments, lines_of
from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.audit.listeners import record_event

router = APIRouter(tags=["Portefeuille (Module 6)"])


@lru_cache
def formats() -> dict[str, dict[str, Any]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "export_ecritures.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}


def _amount(value: Decimal, decimal: str) -> str:
    return "" if not value else f"{value:.2f}".replace(".", decimal)


def render(
    fmt: dict[str, Any], entries: list[tuple[Any, list[Any]]], journal: str, default_date: Any
) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=fmt["separateur"], lineterminator="\r\n")
    if fmt.get("entete"):
        writer.writerow([label for _, label in fmt["colonnes"]])
    for adj, lines in entries:
        for i, ln in enumerate(lines):
            first = i == 0 or not fmt.get("entete_premiere_ligne")
            values = {
                "journal": journal if first else "",
                "date": adj.date_ecriture.strftime(fmt["date"])
                if first and adj.date_ecriture
                else "",
                "piece": f"AJE{adj.numero}" if first else "",
                "compte": ln.compte,
                "libelle": (ln.libelle or adj.libelle)[:60],
                "debit": _amount(ln.debit, fmt["decimale"]),
                "credit": _amount(ln.credit, fmt["decimale"]),
            }
            writer.writerow([values[key] for key, _ in fmt["colonnes"]])
    return out.getvalue().encode(fmt["encodage"], errors="replace")


@router.get("/entry-export-formats")
def list_formats(user: CurrentUser) -> list[dict[str, str]]:
    return [{"code": k, "libelle": v["libelle"]} for k, v in formats().items()]


@router.get("/audit-files/{file_id}/entries-export")
def export_entries(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("generique"),  # noqa: A002
    journal: str = Query("OD", min_length=1, max_length=10),
    toutes: bool = False,
) -> Response:
    """Écritures acceptées du dossier ; par défaut les seules écritures d'inventaire générées
    par les assistants, avec `toutes` les corrections et reclassements acceptés aussi."""
    file, _ = get_file(db, file_id, user)
    _client(db, file)
    fmt = formats().get(format)
    if fmt is None:
        raise HTTPException(422, f"Format inconnu ; formats : {', '.join(formats())}")
    items = [
        a
        for a in file_adjustments(db, file.id)
        if a.statut == "acceptee" and (toutes or a.type == "inventaire")
    ]
    if not items:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucune écriture acceptée à exporter")
    lines = lines_of(db, [a.id for a in items])
    content = render(fmt, [(a, lines[a.id]) for a in items], journal, file.date_fin)
    record_event(
        db,
        "export",
        object_type="AuditFile",
        object_id=file.id,
        details={"ecritures": [a.numero for a in items], "format": format},
    )
    db.commit()
    name = f"ecritures_{file.exercice}_{format}.{fmt['extension']}"
    return Response(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
