import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.audit.listeners  # noqa: F401  (enregistre l'écouteur de journalisation)
from app.api import (
    action_plans,
    analyses,
    attachments,
    audit_log,
    auth,
    contradictory,
    data_links,
    datasets,
    engagement_status,
    engagements,
    evidence,
    findings,
    imports,
    library,
    macros,
    meta,
    notifications,
    plans,
    portal,
    program,
    review_notes,
    risk,
    sampling,
    signoffs,
    teams,
    templates,
    tickmarks,
    timesheets,
    universe,
    users,
    views,
    workpapers,
)
from app.audit.listeners import AuditIntegrityError
from app.config import get_settings
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("auditlab.http")

app = FastAPI(
    title="AuditLab API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    log.info(
        "requête traitée",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            "user_id": getattr(request.state, "user_id", None),
        },
    )
    return response


@app.exception_handler(AuditIntegrityError)
def integrity_error(_: Request, exc: AuditIntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


for router in (
    meta.router,
    auth.router,
    users.router,
    teams.router,
    audit_log.router,
    universe.router,
    risk.router,
    plans.router,
    engagements.router,
    engagements.staff_router,
    engagement_status.router,
    timesheets.router,
    library.router,
    program.router,
    program.my_router,
    templates.router,
    workpapers.router,
    attachments.router,
    tickmarks.router,
    signoffs.router,
    review_notes.router,
    notifications.router,
    datasets.router,
    imports.router,
    views.router,
    analyses.router,
    sampling.router,
    macros.router,
    data_links.router,
    findings.router,
    evidence.router,
    action_plans.router,
    contradictory.router,
    portal.router,
):
    app.include_router(router, prefix="/api")
