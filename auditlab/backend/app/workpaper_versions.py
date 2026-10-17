"""Versions des papiers de travail (AUD-17) : instantanés, empreintes et comparaison."""

import difflib
import hashlib
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.workpaper import Workpaper, WorkpaperVersion
from app.richtext import to_plain_text

VERSIONED_FIELDS = (
    "reference",
    "titre",
    "objectif",
    "travaux",
    "conclusion",
    "evaluation",
    "procedure_id",
)
# Champs comparés en texte, dans l'ordre d'affichage.
COMPARED = (
    ("reference", "Référence"),
    ("titre", "Intitulé"),
    ("objectif", "Objectif"),
    ("travaux", "Travaux réalisés"),
    ("conclusion", "Conclusion"),
    ("evaluation", "Évaluation"),
)


def snapshot(wp: Workpaper) -> dict[str, Any]:
    data = {f: getattr(wp, f) for f in VERSIONED_FIELDS}
    data["procedure_id"] = str(data["procedure_id"]) if data["procedure_id"] else None
    return data


def content_hash(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_version(db: Session, wp: Workpaper) -> WorkpaperVersion:
    content = snapshot(wp)
    version = WorkpaperVersion(
        workpaper_id=wp.id,
        version=wp.version,
        contenu=content,
        hash_contenu=content_hash(content),
        created_by=db.info.get("actor_id"),
    )
    db.add(version)
    return version


def _as_text(field: str, value: Any) -> str:
    if field == "travaux":
        return to_plain_text(value)
    return "" if value is None else str(value)


_TOKEN = re.compile(r"\s+|[^\s]+")


def diff_text(old: str, new: str) -> list[dict[str, str]]:
    """Différences mot à mot : segments égaux, insérés ou supprimés."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    result: list[dict[str, str]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            result.append({"type": "egal", "texte": "".join(a[i1:i2])})
            continue
        if op in ("delete", "replace"):
            result.append({"type": "supprime", "texte": "".join(a[i1:i2])})
        if op in ("insert", "replace"):
            result.append({"type": "ajoute", "texte": "".join(b[j1:j2])})
    return result


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for field, label in COMPARED:
        a, b = _as_text(field, old.get(field)), _as_text(field, new.get(field))
        fields.append(
            {"champ": field, "libelle": label, "modifie": a != b, "segments": diff_text(a, b)}
        )
    return fields
