"""RCO-26 : comparatif N/N-1 des états révisés et indicateurs de gestion remis au client.

Les postes et les indicateurs (chiffre d'affaires, marges, trésorerie, endettement) sont
calculés sur les états après écritures d'inventaire acceptées ; les formules des indicateurs
sont des données par référentiel (`indicateurs_gestion.json`). Variation : écart absolu et
relatif, non significatif quand N-1 est nul.
"""

import json
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.opinion import MEDIA
from app.api.pieces import _closing
from app.audit.listeners import record_event
from app.models.portfolio import Closing
from app.models.revision import AccountingFramework, AuditFile
from app.revision import documents, statements
from app.revision.formula import evaluate
from app.revision.mapping import UnmappedError, file_values
from app.revision.reports import amount

router = APIRouter(tags=["Portefeuille (Module 6)"])
DATA = Path(__file__).parents[1] / "cabinet" / "data" / "indicateurs_gestion.json"
PRECISION = {"montant": Decimal("1"), "pourcentage": Decimal("0.1"), "ratio": Decimal("0.01")}


def definitions(framework_code: str) -> list[dict[str, str]]:
    return json.loads(DATA.read_text("utf-8"))["referentiels"].get(framework_code, [])


def _q(value: Decimal | None, unit: str) -> str | None:
    if value is None:
        return None
    if unit == "pourcentage":
        value *= 100
    return str(value.quantize(PRECISION[unit], ROUND_HALF_UP))


def variation(n: Decimal | None, n1: Decimal | None) -> dict[str, str | None]:
    if n is None or n1 is None:
        return {"variation": None, "variation_pct": None}
    pct = None if n1 == 0 else ((n - n1) / abs(n1) * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return {"variation": str(n - n1), "variation_pct": None if pct is None else str(pct)}


def build(db: Session, closing: Closing) -> dict[str, Any]:
    file = db.get(AuditFile, closing.audit_file_id)
    fw = db.get(AccountingFramework, file.framework_id)
    try:
        values = file_values(db, file, adjusted=True)
        states = statements.build(db, file)
    except UnmappedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    has_n1 = any(values["N-1"].values())
    indicators = []
    for d in definitions(fw.code):
        n = evaluate(d["formule"], values["N"])
        n1 = evaluate(d["formule"], values["N-1"]) if has_n1 else None
        unit = d["unite"]
        gap = None if n is None or n1 is None else n - n1
        # Montant : écart absolu et relatif ; sinon écart en points ou en valeur du ratio.
        pct = variation(n, n1)["variation_pct"] if unit == "montant" else None
        delta = {"variation": _q(gap, unit), "variation_pct": pct}
        indicators.append(
            {
                **{k: d[k] for k in ("code", "libelle", "famille", "unite")},
                "N": _q(n, unit),
                "N-1": _q(n1, unit),
                **delta,
            }
        )
    lines = []
    for etat, rows in states["etats"].items():
        for ln in rows:
            n = Decimal(ln["N"])
            n1 = Decimal(ln["N-1"]) if ln["N-1"] is not None and has_n1 else None
            lines.append(
                {"etat": etat, "code": ln["code"], "libelle": ln["libelle"], "total": ln["total"],
                 "N": ln["N"], "N-1": None if n1 is None else ln["N-1"], **variation(n, n1)}
            )  # fmt: skip
    return {
        "exercice": closing.exercice,
        "devise": file.devise,
        "n1_disponible": has_n1,
        "indicateurs": indicators,
        "comparatif": lines,
    }


@router.get("/closings/{closing_id}/management")
def read_management(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, _ = _closing(db, closing_id, user)
    return build(db, closing)


def _fmt(value: str | None, unit: str = "montant") -> str:
    if value is None:
        return "n.s."
    if unit == "montant":
        return amount(Decimal(value))
    return value.replace(".", ",") + (" %" if unit == "pourcentage" else "")


@router.get("/closings/{closing_id}/management/export")
def export_management(
    closing_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    closing, client = _closing(db, closing_id, user)
    data = build(db, closing)
    n, n1 = str(closing.exercice), str(closing.exercice - 1)
    pct = lambda v: "n.s." if v is None else v.replace(".", ",") + " %"  # noqa: E731
    blocks: list[dict[str, Any]] = [
        {"titre": "Indicateurs de gestion", "niveau": 1},
        {"texte": f"{client.raison_sociale} – montants en {data['devise']}."},
        {
            "tableau": [["Indicateur", n, n1, "Variation"]]
            + [
                [
                    i["libelle"],
                    _fmt(i["N"], i["unite"]),
                    _fmt(i["N-1"], i["unite"]),
                    pct(i["variation_pct"])
                    if i["unite"] == "montant"
                    else _fmt(i["variation"], i["unite"]),
                ]
                for i in data["indicateurs"]
            ],  # fmt: skip
            "entete": True,
        },
        {"saut": True},
        {"titre": f"Comparatif {n} / {n1}", "niveau": 1},
    ]
    for etat in dict.fromkeys(ln["etat"] for ln in data["comparatif"]):
        rows = [ln for ln in data["comparatif"] if ln["etat"] == etat]
        blocks.append({"titre": statements.ETATS.get(etat, etat), "niveau": 2})
        blocks.append(
            {
                "tableau": [["Poste", n, n1, "Variation", "%"]]
                + [
                    [
                        f"{ln['code']} {ln['libelle']}",
                        _fmt(ln["N"]),
                        _fmt(ln["N-1"]),
                        _fmt(ln["variation"]),
                        pct(ln["variation_pct"]),
                    ]
                    for ln in rows
                ],  # fmt: skip
                "entete": True,
            }
        )
    content = documents.render(format, f"Comparatif et indicateurs – exercice {n}", blocks)
    record_event(
        db,
        "export",
        object_type="Closing",
        object_id=closing.id,
        details={"document": "indicateurs"},
    )
    db.commit()
    return Response(
        content,
        media_type=MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="indicateurs_{n}.{format}"'},
    )
