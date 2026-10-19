"""Scripts Python d'analyse d'une mission (DAT-26) : édition, exécution, historique."""

import inspect
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.datasets import require_analyst, require_read
from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import get_engagement
from app.models.data import Dataset, Script, ScriptRun, ScriptTemplate, Upload
from app.models.engagement import Engagement
from app.models.user import User
from app.scripting.runner import inputs_out, sha256_text

router = APIRouter(tags=["Scripts"])
MAX_CODE = 200_000


class Entry(BaseModel):
    type: Literal["table", "fichier"]
    id: uuid.UUID


class ScriptIn(BaseModel):
    nom: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    code: str = Field(max_length=MAX_CODE)
    entrees: list[Entry] = Field(default_factory=list, max_length=20)


def _check(db: Session, engagement: Engagement, body: ScriptIn) -> list[dict[str, str]]:
    try:
        compile(body.code, "script.py", "exec")  # syntaxe seulement : rien n'est exécuté
    except SyntaxError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Erreur de syntaxe ligne {exc.lineno} : {exc.msg}",
        ) from exc
    entries = []
    for e in body.entrees:
        obj = db.get(Dataset if e.type == "table" else Upload, e.id)
        if obj is None or obj.deleted_at is not None or obj.engagement_id != engagement.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Entrée inconnue ou hors de la mission"
            )
        entries.append({"type": e.type, "id": str(e.id)})
    return entries


def script_out(db: Session, s: Script) -> dict[str, Any]:
    last = db.scalar(
        select(ScriptRun)
        .where(ScriptRun.script_id == s.id, ScriptRun.deleted_at.is_(None))
        .order_by(ScriptRun.created_at.desc())
        .limit(1)
    )
    return {
        "id": str(s.id),
        "engagement_id": str(s.engagement_id),
        "nom": s.nom,
        "description": s.description,
        "code": s.code,
        "entrees": inputs_out(db, s.entrees),
        "modele": None
        if s.modele_id is None
        else {
            "id": str(s.modele_id),
            "version": s.modele_version,
            "reference": db.get(ScriptTemplate, s.modele_id).reference,
        },
        "derniere_execution": run_out(db, last) if last else None,
    }


def run_out(db: Session, r: ScriptRun) -> dict[str, Any]:
    tables = [db.get(Dataset, uuid.UUID(i)) for i in r.tables]
    return {
        "id": str(r.id),
        "script_id": str(r.script_id),
        "statut": r.statut,
        "declenchement": r.declenchement,
        "code_sha256": r.code_sha256,
        "entrees": inputs_out(db, r.entrees),
        "debut": r.debut.isoformat() if r.debut else None,
        "cree_le": r.created_at.isoformat(),
        "duree_ms": r.duree_ms,
        "sortie": r.sortie,
        "erreur": r.erreur,
        "indicateurs": r.indicateurs,
        "tables": [{"id": str(t.id), "nom": t.nom, "nb_lignes": t.nb_lignes} for t in tables if t],
        "par": db.get(User, r.created_by).nom if r.created_by else None,
    }


def get_script(db: Session, script_id: uuid.UUID, user: User) -> tuple[Script, Engagement]:
    s = db.get(Script, script_id)
    if s is None or s.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script introuvable")
    engagement = get_engagement(db, s.engagement_id, user)
    require_read(engagement, user)
    return s, engagement


@router.get("/scripts/api")
def sdk_reference(user: CurrentUser) -> list[dict[str, str]]:
    """Fonctions de l'API `audit` et leur documentation (aide de l'éditeur)."""
    from app.scripting.sdk import audit

    return [
        {"nom": f"audit.{name}", "signature": f"audit.{name}{inspect.signature(fn)}",
         "doc": inspect.getdoc(fn) or ""}
        for name in audit.__all__
        if (fn := getattr(audit, name))
    ]  # fmt: skip


@router.get("/engagements/{engagement_id}/scripts")
def list_scripts(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict]:
    engagement = get_engagement(db, engagement_id, user)
    require_read(engagement, user)
    rows = db.scalars(
        select(Script)
        .where(Script.engagement_id == engagement.id, Script.deleted_at.is_(None))
        .order_by(Script.nom)
    )
    return [script_out(db, s) for s in rows]


@router.post("/engagements/{engagement_id}/scripts", status_code=status.HTTP_201_CREATED)
def create_script(
    engagement_id: uuid.UUID, body: ScriptIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    engagement = get_engagement(db, engagement_id, user)
    require_analyst(engagement, user)
    entries = _check(db, engagement, body)
    s = Script(engagement_id=engagement.id, nom=body.nom, description=body.description,
               code=body.code, entrees=entries)  # fmt: skip
    db.add(s)
    db.commit()
    return script_out(db, s)


@router.get("/scripts/{script_id}")
def read_script(script_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    s, _ = get_script(db, script_id, user)
    return script_out(db, s)


@router.put("/scripts/{script_id}")
def update_script(
    script_id: uuid.UUID, body: ScriptIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    s, engagement = get_script(db, script_id, user)
    require_analyst(engagement, user)
    s.entrees = _check(db, engagement, body)
    s.nom, s.description, s.code = body.nom, body.description, body.code
    db.commit()
    return script_out(db, s)


@router.delete("/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(script_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    import datetime as dt

    s, engagement = get_script(db, script_id, user)
    require_analyst(engagement, user)
    s.deleted_at, s.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


def start_run(db: Session, s: Script, user_id: uuid.UUID | None, trigger: str) -> ScriptRun:
    """Fige le code et les entrées du script et lance l'exécution en tâche de fond."""
    from app.analytics.jobs import run_script

    run = ScriptRun(script_id=s.id, engagement_id=s.engagement_id, statut="en_cours",
                    declenchement=trigger, code=s.code, code_sha256=sha256_text(s.code),
                    entrees=s.entrees, created_by=user_id)  # fmt: skip
    db.add(run)
    db.commit()
    run_script.delay(str(run.id))
    db.refresh(run)
    return run


@router.post("/scripts/{script_id}/runs", status_code=status.HTTP_202_ACCEPTED)
def launch(script_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    s, engagement = get_script(db, script_id, user)
    require_analyst(engagement, user)
    return run_out(db, start_run(db, s, user.id, "manuel"))


@router.get("/scripts/{script_id}/runs")
def list_runs(script_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    s, _ = get_script(db, script_id, user)
    rows = db.scalars(
        select(ScriptRun)
        .where(ScriptRun.script_id == s.id, ScriptRun.deleted_at.is_(None))
        .order_by(ScriptRun.created_at.desc())
        .limit(50)
    )
    return [run_out(db, r) for r in rows]


@router.get("/script-runs/{run_id}")
def read_run(run_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    r = db.get(ScriptRun, run_id)
    if r is None or r.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exécution introuvable")
    get_script(db, r.script_id, user)
    return run_out(db, r)
