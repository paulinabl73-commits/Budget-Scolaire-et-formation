"""Lecture des fichiers de travail des assistants du Module 6 (inventaire, entrées de stock,
relevés fiscaux…) : colonnes reconnues par synonymes, montants au format français ou anglais."""

from typing import Any

from fastapi import HTTPException

from app.revision.balances import ImportError_, normalize, parse_amount, parse_date, read_rows


def read_table(
    content: bytes,
    filename: str,
    fields: dict[str, tuple[str, ...]],
    required: tuple[str, ...],
    amounts: tuple[str, ...] = (),
    dates: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Lignes du fichier en dictionnaires ; l'en-tête est la première ligne qui porte toutes
    les colonnes obligatoires (reconnues par leur nom ou un synonyme)."""
    try:
        rows = read_rows(content, filename)
    except ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    names = {normalize(s): f for f, synonyms in fields.items() for s in (f, *synonyms)}
    header, cols = None, {}
    for index, row in enumerate(rows[:30]):
        found = {names[normalize(h)]: j for j, h in enumerate(row) if normalize(h) in names}
        if set(required) <= set(found):
            header, cols = index, found
            break
    if header is None:
        raise HTTPException(422, f"Colonnes attendues : {', '.join(required)}")
    out = []
    for row in rows[header + 1 :]:
        item: dict[str, Any] = {}
        for f, j in cols.items():
            value = row[j] if j < len(row) else None
            if f in amounts:
                try:
                    value = str(parse_amount(value))
                except Exception as exc:  # noqa: BLE001
                    raise HTTPException(422, f"Montant illisible « {value} » ({f})") from exc
            elif f in dates:
                parsed = parse_date(value)
                value = parsed.isoformat() if parsed else None
            else:
                value = str(value).strip() if value not in (None, "") else None
            item[f] = value
        if any(item.get(f) for f in required):
            out.append(item)
    if not out:
        raise HTTPException(422, "Aucune ligne lue")
    return out
