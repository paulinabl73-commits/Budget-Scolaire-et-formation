"""Passage aux IFRS : retraitements (IFR-01) et états IFRS avec réconciliations (IFR-03)."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.adjustments import adjustment_out, file_adjustments, lines_of
from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession
from app.api.mapping import values_or_409
from app.audit.listeners import record_event
from app.models.revision import AccountingFramework, AuditFile, IfrsChecklistAnswer, StatementLine
from app.revision import documents, ifrs, ifrs_assistants, statements
from app.revision.mapping import file_values

router = APIRouter(tags=["Révision – IFRS"])
ZERO = Decimal(0)
ETATS = {
    "ifrs_situation": "État de la situation financière",
    "ifrs_resultat": "État du résultat global",
    "ifrs_capitaux": "État des variations des capitaux propres",
    "ifrs_flux": "Tableau des flux de trésorerie",
}
NO_COMPARATIVE = ("ifrs_capitaux", "ifrs_flux")
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def ifrs_framework(db: Session, file: AuditFile) -> AccountingFramework:
    fw = db.get(AccountingFramework, file.ifrs_framework_id) if file.ifrs_framework_id else None
    if fw is None:
        fw = db.scalar(
            select(AccountingFramework)
            .where(
                AccountingFramework.code == "IFRS",
                AccountingFramework.actif.is_(True),
                AccountingFramework.deleted_at.is_(None),
            )
            .order_by(AccountingFramework.date_effet.desc())
        )
    if fw is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun référentiel de restitution IFRS")
    return fw


def build(db: Session, file: AuditFile) -> dict[str, Any]:
    values_or_409(db, file)
    fw = ifrs_framework(db, file)
    lines = list(
        db.scalars(
            select(StatementLine)
            .where(StatementLine.framework_id == fw.id)
            .order_by(StatementLine.etat, StatementLine.ordre)
        )
    )
    before = file_values(db, file, adjusted=True)
    after = file_values(db, file, adjusted=True, ifrs=True)
    n1 = ifrs.evaluate_lines(lines, after["N-1"], None)
    n = ifrs.evaluate_lines(lines, after["N"], {**after["N-1"], **n1})
    states: dict[str, list[dict[str, Any]]] = {}
    for ln in lines:
        states.setdefault(ln.etat, []).append(
            {
                "code": ln.code,
                "libelle": ln.libelle,
                "niveau": ln.niveau,
                "passage": ln.formule,
                "total": ln.niveau == 0,
                "N": str(n.get(ln.code, ZERO)),
                "N-1": None if ln.etat in NO_COMPARATIVE else str(n1.get(ln.code, ZERO)),
            }
        )
    restatements = [a for a in file_adjustments(db, file.id, ifrs=True) if a.statut == "acceptee"]
    effects = ifrs.effects_by_standard(restatements, lines_of(db, [a.id for a in restatements]))
    cp_before, xi_before = before["N"].get("CP", ZERO), before["N"].get("XI", ZERO)
    grants = n.get("ID4", ZERO)
    equity = [{"libelle": "Capitaux propres SYSCOHADA révisés", "montant": str(cp_before)}]
    equity += [
        {"libelle": f"Retraitements {norme}", "montant": str(e["capitaux"])}
        for norme, e in sorted(effects.items())
        if e["capitaux"]
    ]
    equity.append(
        {
            "libelle": "Subventions d'investissement présentées en produits différés (IAS 20)",
            "montant": str(-grants),
        }
    )
    explained = cp_before + sum((e["capitaux"] for e in effects.values()), ZERO) - grants
    result = [{"libelle": "Résultat SYSCOHADA révisé", "montant": str(xi_before)}]
    result += [
        {"libelle": f"Retraitements {norme}", "montant": str(e["resultat"])}
        for norme, e in sorted(effects.items())
        if e["resultat"]
    ]
    explained_result = xi_before + sum((e["resultat"] for e in effects.values()), ZERO)
    return {
        "referentiel": f"{fw.libelle} ({fw.version})",
        "etats": {k: states[k] for k in ETATS if k in states},
        "controles": statements.checks(fw.regles, {"N": n, "N-1": n1}),
        "reconciliation": {
            "capitaux": {
                "lignes": equity,
                "ifrs": str(n.get("ICZ", ZERO)),
                "ecart": str(n.get("ICZ", ZERO) - explained),
            },
            "resultat": {
                "lignes": result,
                "ifrs": str(n.get("IRN", ZERO)),
                "ecart": str(n.get("IRN", ZERO) - explained_result),
            },
        },
    }


@router.get("/audit-files/{file_id}/ifrs")
def read_ifrs(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    data = build(db, file)
    items = file_adjustments(db, file.id, ifrs=True)
    lines = lines_of(db, [a.id for a in items])
    return {**data, "retraitements": [adjustment_out(a, lines[a.id], db) for a in items]}


def _fr(value: str | None) -> str:
    return "" if value is None else f"{Decimal(value):,.0f}".replace(",", " ")


@router.get("/audit-files/{file_id}/ifrs/export")
def export_ifrs(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    file, _ = get_file(db, file_id, user)
    data = build(db, file)
    blocks: list[dict[str, Any]] = [{"texte": data["referentiel"]}]
    for etat, rows in data["etats"].items():
        blocks += [
            {"titre": ETATS[etat]},
            {
                "tableau": [["Poste", "N", "N-1"]]
                + [[r["libelle"], _fr(r["N"]), _fr(r["N-1"])] for r in rows]
            },
        ]
    for key, title in (
        ("capitaux", "Réconciliation des capitaux propres"),
        ("resultat", "Réconciliation du résultat"),
    ):
        rec = data["reconciliation"][key]
        blocks += [
            {"titre": title},
            {
                "tableau": [["Élément", "Montant"]]
                + [[r["libelle"], _fr(r["montant"])] for r in rec["lignes"]]
                + [["IFRS", _fr(rec["ifrs"])]]
            },
        ]
    content = documents.render(format, f"États financiers IFRS – exercice {file.exercice}", blocks)
    record_event(db, "export", object_type="AuditFile", object_id=file.id, details={"ifrs": format})
    db.commit()
    return Response(
        content,
        media_type=MEDIA[format],
        headers={
            "Content-Disposition": f'attachment; filename="etats_ifrs_{file.exercice}.{format}"'
        },
    )


# --- Assistants de calcul (IFR-02) --------------------------------------------------------------


class AssistantIn(BaseModel):
    parametres: dict[str, Any] = Field(default_factory=dict)
    creer: bool = False


@router.get("/ifrs/assistants")
def list_assistants(user: CurrentUser) -> list[dict[str, Any]]:
    return [
        {
            "code": code,
            "norme": spec["norme"],
            "params": [{"nom": p.nom, "type": p.type, "defaut": p.defaut} for p in spec["params"]],
        }
        for code, spec in ifrs_assistants.ASSISTANTS.items()
    ]


def _prefill(
    db: Session, file: AuditFile, code: str, params: dict[str, Any], user: Any
) -> dict[str, Any]:
    params = dict(params)
    if code == "ias12" and ("effet_resultat" not in params or "effet_capitaux" not in params):
        others = [
            a
            for a in file_adjustments(db, file.id, ifrs=True)
            if a.statut == "acceptee" and a.norme != "IAS 12"
        ]
        effects = ifrs.effects_by_standard(others, lines_of(db, [a.id for a in others]))
        params.setdefault(
            "effet_resultat", str(sum((e["resultat"] for e in effects.values()), ZERO))
        )
        params.setdefault(
            "effet_capitaux", str(sum((e["capitaux"] for e in effects.values()), ZERO))
        )
    if code == "ifrs9" and not params.get("tranches") and params.get("taux_perte"):
        from app.api.third_parties import receivables_aging

        aging = receivables_aging(file.id, user, db)
        params["tranches"] = [
            {"libelle": b["libelle"], "montant": total, "taux_perte": rate}
            for b, total, rate in zip(
                aging["tranches"], aging["totaux"], params["taux_perte"], strict=False
            )
        ]
        params.setdefault("depreciation_comptabilisee", aging["depreciation_comptabilisee"])
    return params


@router.post("/audit-files/{file_id}/ifrs/assistants/{code}")
def run_assistant(
    file_id: uuid.UUID, code: str, body: AssistantIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    from app.api.adjustments import AdjustmentIn, create_adjustment
    from app.revision.currency import decimals, quantum

    file, engagement = get_file(db, file_id, user)
    params = _prefill(db, file, code, body.parametres, user)
    try:
        result = ifrs_assistants.run(code, params, quantum(decimals(db, file.devise)))
    except ifrs_assistants.AssistantError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.creer:
        if not result["lignes"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Aucun écart : pas d'écriture à proposer")
        entry = AdjustmentIn(
            type="retraitement_ifrs",
            norme=result["norme"],
            date_ecriture=file.date_fin,
            libelle=result["libelle"],
            justification=f"Calcul de l'assistant {result['norme']} (IFR-02) : "
            + ", ".join(
                f"{k} = {v}" for k, v in result["calcul"].items() if not isinstance(v, list)
            ),
            lignes=result["lignes"],
        )
        result["retraitement"] = create_adjustment(file.id, entry, user, db)
    return result


# --- Check-list des informations à fournir (IFR-04) ---------------------------------------------


class AnswerIn(BaseModel):
    reponse: str = Field(pattern="^(oui|non|na)$")
    commentaire: str | None = Field(default=None, max_length=5000)


def _checklist() -> list[dict[str, Any]]:
    import json
    from pathlib import Path

    path = Path(ifrs.__file__).parent / "data" / "ifrs_checklist.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "norme": n["norme"],
            "toujours": n.get("toujours", False),
            "points": [
                {"code": f"{n['norme']}-{i:02d}", "libelle": p}
                for i, p in enumerate(n["points"], 1)
            ],
        }
        for n in doc["normes"]
    ]


def _answers(db: Session, file_id: uuid.UUID) -> dict[str, IfrsChecklistAnswer]:
    rows = db.scalars(
        select(IfrsChecklistAnswer).where(
            IfrsChecklistAnswer.audit_file_id == file_id, IfrsChecklistAnswer.deleted_at.is_(None)
        )
    )
    return {a.code: a for a in rows}


def checklist_out(db: Session, file: AuditFile) -> dict[str, Any]:
    answers = _answers(db, file.id)
    used = {a.norme for a in file_adjustments(db, file.id, ifrs=True) if a.statut == "acceptee"}
    groups, total, done, missing = [], 0, 0, 0
    for n in _checklist():
        points = []
        for p in n["points"]:
            a = answers.get(p["code"])
            points.append(
                {
                    **p,
                    "reponse": a.reponse if a else None,
                    "commentaire": a.commentaire if a else None,
                }
            )
            total += 1
            done += a is not None
            missing += a is not None and a.reponse == "non"
        groups.append(
            {
                "norme": n["norme"],
                "applicable": n["toujours"] or n["norme"] in used,
                "points": points,
            }
        )
    return {"normes": groups, "total": total, "repondus": done, "informations_manquantes": missing}


@router.get("/audit-files/{file_id}/ifrs/checklist")
def read_checklist(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return checklist_out(db, file)


@router.put("/audit-files/{file_id}/ifrs/checklist/{code}")
def answer(
    file_id: uuid.UUID, code: str, body: AnswerIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    from app.api.audit_files import require_work

    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    if code not in {p["code"] for n in _checklist() for p in n["points"]}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Point de check-list inconnu")
    if body.reponse == "non" and not (body.commentaire or "").strip():
        raise HTTPException(422, "Information manquante : précisez-la en commentaire")
    a = _answers(db, file.id).get(code)
    if a is None:
        a = IfrsChecklistAnswer(
            engagement_id=file.engagement_id, audit_file_id=file.id, code=code, reponse=body.reponse
        )
        db.add(a)
    a.reponse, a.commentaire = body.reponse, body.commentaire
    db.commit()
    return checklist_out(db, file)
