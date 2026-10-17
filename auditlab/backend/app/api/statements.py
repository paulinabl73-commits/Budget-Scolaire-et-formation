"""États financiers révisés, avant et après ajustements (REV-23), avec contrôles de cohérence
(REV-24) ; export Excel et PDF, journalisé."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.audit_files import get_file
from app.api.deps import CurrentUser, DbSession
from app.api.mapping import values_or_409
from app.audit.listeners import record_event
from app.revision import statements

router = APIRouter(tags=["Révision – états financiers"])
MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/audit-files/{file_id}/statements")
def read_statements(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    values_or_409(db, file)  # REV-10 : refus tant qu'un compte n'est pas affecté
    return statements.build(db, file)


@router.get("/audit-files/{file_id}/statements/export")
def export_statements(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query(pattern="^(xlsx|pdf)$"),  # noqa: A002 - nom du paramètre d'URL
) -> Response:
    file, _ = get_file(db, file_id, user)
    values_or_409(db, file)
    data = statements.build(db, file)
    if not all(c["ok"] for c in data["controles"]):
        failed = [c["libelle"] for c in data["controles"] if not c["ok"]]
        raise HTTPException(409, f"États incohérents : {' ; '.join(failed)}")
    title = f"États financiers révisés – {file.exercice}"
    content = (statements.to_excel if format == "xlsx" else statements.to_pdf)(data, title)
    record_event(db, "export", object_type="AuditFile", object_id=file.id,
                 details={"etats_financiers": format})  # fmt: skip
    db.commit()
    name = f"etats_financiers_{file.exercice}.{format}"
    return Response(content, media_type=MEDIA[format],
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})  # fmt: skip
