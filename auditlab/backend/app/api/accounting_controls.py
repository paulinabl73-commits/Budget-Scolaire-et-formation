"""Contrôles automatiques de la comptabilité sur balance et grand livre (RCO-08).

Balance : comptes à solde anormal selon le sens normal de leur racine (données
cabinet/data/soldes_anormaux.json). Grand livre : comptes de tiers non lettrés (lettrage du
REV-18) ; écritures sans pièce, ruptures de numérotation des pièces par journal et doublons
d'écritures lancés comme analyses du Module 2 (traçables, rattachables aux papiers).
"""

import json
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.third_parties import _ledger
from app.config import get_settings
from app.models.data import Dataset
from app.models.revision import AccountingFramework
from app.revision.imports import active_balance
from app.revision.mapping import assignments
from app.revision.third_parties import match

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
CONTROL = "RCO-08"


@lru_cache
def rules() -> dict[str, list[dict[str, Any]]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "soldes_anormaux.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def abnormal(compte: str, solde: Decimal, framework_rules: list[dict[str, Any]]) -> str | None:
    """Libellé de l'anomalie si le solde n'est pas dans le sens normal de sa racine."""
    rule = max(
        (r for r in framework_rules if compte.startswith(r["racine"])),
        key=lambda r: len(r["racine"]),
        default=None,
    )
    if rule is None or any(compte.startswith(x) for x in rule.get("exclusions", [])):
        return None
    wrong = {"debit": solde < 0, "credit": solde > 0, "nul": solde != 0}[rule["attendu"]]
    return rule["libelle"] if wrong else None


def _runs(db: Any, file: Any) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Dataset)
        .where(Dataset.engagement_id == file.engagement_id, Dataset.deleted_at.is_(None))
        .order_by(Dataset.created_at.desc())
    )
    return [
        {
            "id": str(d.id),
            "nom": d.nom,
            "statut": d.statut,
            "nb_lignes": d.nb_lignes,
            "operation": d.operation,
            "resultat": d.resultat,
        }  # fmt: skip
        for d in rows
        if d.definition.get("dossier") == str(file.id) and d.definition.get("controle") == CONTROL
    ][:6]


@router.get("/audit-files/{file_id}/accounting-controls")
def read_controls(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    code = db.get(AccountingFramework, file.framework_id).code
    framework_rules = rules().get(code, [])
    abnormal_rows = []
    for a in assignments(db, file):
        solde = a.soldes.get("N")
        if solde is None:
            continue
        label = abnormal(a.compte, solde, framework_rules)
        if label:
            abnormal_rows.append(
                {"compte": a.compte, "libelle": a.libelle, "solde": str(solde), "anomalie": label}
            )
    try:
        frame = _ledger(db, file)
    except HTTPException:
        frame = None
    tiers = None
    if frame is not None:
        states = match(frame, get_settings().racines_tiers)
        tiers = [
            {
                "compte": compte,
                "lignes_non_lettrees": len(s.ouvertes),
                "montant_non_lettre": str(sum((i.net for i in s.ouvertes), ZERO)),
                "plus_ancienne": min(
                    (i.date for i in s.ouvertes if i.date), default=None
                ).isoformat()
                if any(i.date for i in s.ouvertes)
                else None,
                "anomalies": s.anomalies,
            }
            for compte, s in sorted(states.items())
            if s.ouvertes or s.anomalies
        ]
    return {
        "regles_disponibles": bool(framework_rules),
        "soldes_anormaux": abnormal_rows,
        "grand_livre": frame is not None,
        "tiers_non_lettres": tiers,
        "analyses": _runs(db, file),
    }


@router.post(
    "/audit-files/{file_id}/accounting-controls/ledger", status_code=status.HTTP_202_ACCEPTED
)
def launch_ledger_controls(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Lance sur le grand livre N : écritures sans pièce, ruptures de numérotation des pièces
    par journal et doublons d'écritures (analyses du Module 2)."""
    from app.api.analyses import AnalysisIn, launch

    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    gl = active_balance(db, file.id, "N", "grand_livre")
    if gl is None or gl.dataset_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun grand livre N accepté")
    columns = {c["nom"] for c in db.get(Dataset, gl.dataset_id).schema}
    launches: list[tuple[str, dict[str, Any], str]] = []
    skipped = []
    if "piece" in columns:
        launches.append(("extraction", {"expression": "piece EST VIDE"}, "Écritures sans pièce"))
        seq = {"champ": "piece", "distinctes": "oui"}
        if "journal" in columns:
            seq["groupe"] = "journal"
        launches.append(("sequence", seq, "Ruptures de numérotation des pièces"))
    else:
        skipped += ["Écritures sans pièce", "Ruptures de numérotation des pièces"]
    keys = [
        c
        for c in ("date", "journal", "piece", "compte", "libelle", "debit", "credit")
        if c in columns
    ]
    launches.append(("doublons", {"cles": keys}, "Doublons d'écritures"))
    out = []
    for operation, params, label in launches:
        ds = launch(
            gl.dataset_id,
            AnalysisIn(
                operation=operation, parametres=params, nom=f"{label} – exercice {file.exercice}"
            ),
            user,
            db,
        )
        dataset = db.get(Dataset, ds.id)
        dataset.definition = {**dataset.definition, "dossier": str(file.id), "controle": CONTROL}
        out.append({"controle": label, "dataset_id": str(ds.id)})
    db.commit()
    return {"lances": out, "non_appliques": skipped}
