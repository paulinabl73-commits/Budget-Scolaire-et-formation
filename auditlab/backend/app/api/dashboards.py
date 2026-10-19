"""Tableaux de bord (REP-04 à REP-06), filtres par période, entité et criticité (REP-08)."""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession, require
from app.api.mission_access import get_engagement
from app.audit.listeners import record_event
from app.models.user import User
from app.reporting import dashboards
from app.reporting.dashboards import Filters
from app.security.roles import Perm

router = APIRouter(prefix="/dashboards", tags=["Tableaux de bord"])
Direction = Annotated[User, Depends(require(Perm.DASHBOARDS_GLOBAL))]


def filters(
    debut: dt.date | None = None,
    fin: dt.date | None = None,
    entity_id: uuid.UUID | None = None,
    criticite: str | None = Query(None, pattern="^(faible|moyenne|elevee|critique)$"),
) -> Filters:
    if debut and fin and fin < debut:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Période incohérente")
    return Filters(debut, fin, entity_id, criticite)


Filtered = Annotated[Filters, Depends(filters)]


@router.get("/direction")
def direction(user: Direction, db: DbSession, f: Filtered) -> dict[str, Any]:
    return dashboards.direction(db, user, f)


@router.get("/recommendations")
def recommendations(user: Direction, db: DbSession, f: Filtered) -> dict[str, Any]:
    return dashboards.recommendations(db, user, f)


@router.get("/missions/{engagement_id}")
def mission(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Tableau de bord d'une mission : son équipe et la Direction (missions visibles)."""
    return dashboards.mission(db, get_engagement(db, engagement_id, user))


@router.get("/committee")
def committee(
    user: Direction,
    db: DbSession,
    annee: int = Query(ge=2000, le=2100),
    trimestre: int = Query(ge=1, le=4),
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    """REP-07 : synthèse trimestrielle pour le comité d'audit."""
    from app.api.opinion import MEDIA
    from app.api.report_templates import default_template
    from app.reporting.committee import build
    from app.revision import documents

    template = default_template(db)
    organisation = (template.page_garde or {}).get("organisation") if template else None
    title, blocks = build(
        db, user, annee, trimestre, organisation or "Direction de l'audit interne"
    )
    footer = f"{title} – document confidentiel destiné au comité d'audit"
    content = documents.render(format, "", blocks, footer)
    record_event(db, "export", object_type="Dashboard", details={"comite": f"T{trimestre} {annee}"})
    db.commit()
    name = f"comite_audit_{annee}_T{trimestre}.{format}"
    return Response(
        content,
        media_type=MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(db: DbSession, name: str, described: dict[str, Any], sheets: list) -> Response:
    from app.reporting.excel import filter_rows, to_xlsx

    content = to_xlsx(filter_rows(db, described), sheets)
    record_event(db, "export", object_type="Dashboard", details={"tableau": name})
    db.commit()
    return Response(
        content, media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="tableau_{name}.xlsx"'},
    )  # fmt: skip


@router.get("/direction/export")
def export_direction(user: Direction, db: DbSession, f: Filtered) -> Response:
    """REP-08 : tableau de bord Direction au format Excel, avec les filtres appliqués."""
    from app.reporting.excel import direction_sheets

    data = dashboards.direction(db, user, f)
    return _xlsx(db, "direction", data["filtres"], direction_sheets(data))


@router.get("/recommendations/export")
def export_recommendations(user: Direction, db: DbSession, f: Filtered) -> Response:
    from app.reporting.excel import recommendations_sheets

    data = dashboards.recommendations(db, user, f)
    return _xlsx(db, "recommandations", data["filtres"], recommendations_sheets(data))


@router.get("/missions/{engagement_id}/export")
def export_mission(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    from app.reporting.excel import mission_sheets

    engagement = get_engagement(db, engagement_id, user)
    data = dashboards.mission(db, engagement)
    return _xlsx(db, f"mission_{engagement.reference}", {}, mission_sheets(data))
