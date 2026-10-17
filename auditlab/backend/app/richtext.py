"""Outils sur les documents riches des papiers de travail (format ProseMirror / TipTap)."""

from typing import Any

EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": []}


def from_plain_text(text: str) -> dict[str, Any]:
    """Document d'un paragraphe par ligne non vide."""
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        for line in text.splitlines()
        if line.strip()
    ]
    return {"type": "doc", "content": paragraphs}


def is_valid_doc(doc: Any) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("type") == "doc"
        and isinstance(doc.get("content", []), list)
    )


def to_plain_text(node: dict[str, Any] | None) -> str:
    """Texte brut d'un document : un bloc par ligne, cellules séparées par des tabulations."""
    if not node:
        return ""
    kind = node.get("type")
    if kind == "text":
        return node.get("text", "")
    if kind == "tickmark":
        return f"[{node.get('attrs', {}).get('symbole', '')}]"
    if kind == "image":
        return f"[image {node.get('attrs', {}).get('alt') or ''}]".replace(" ]", "]")
    if kind == "hardBreak":
        return "\n"
    children = [to_plain_text(c) for c in node.get("content", [])]
    if kind in ("doc", "bulletList", "orderedList", "table"):
        return "\n".join(c for c in children if c != "")
    if kind == "tableRow":
        return "\t".join(children)
    if kind == "listItem":
        return "- " + "\n".join(children)
    return "".join(children)


# AUD-14 : seuls ces nœuds et marques sont admis (pas de HTML brut, pas de script).
ALLOWED_NODES = {
    "doc",
    "paragraph",
    "text",
    "heading",
    "bulletList",
    "orderedList",
    "listItem",
    "blockquote",
    "horizontalRule",
    "hardBreak",
    "table",
    "tableRow",
    "tableCell",
    "tableHeader",
    "image",
    "tickmark",
}
ALLOWED_MARKS = {"bold", "italic", "underline", "strike", "link", "code"}
LINK_PREFIXES = ("https://", "http://", "mailto:", "/missions/")
IMAGE_PREFIX = "attachment:"


class InvalidDocument(ValueError):
    pass


def tickmark_ids(doc: dict[str, Any] | None) -> set[str]:
    """Identifiants des marques de révision utilisées dans un document."""
    found: set[str] = set()
    stack = [doc] if doc else []
    while stack:
        node = stack.pop()
        if node.get("type") == "tickmark":
            found.add(str((node.get("attrs") or {}).get("id", "")))
        stack.extend(node.get("content", []) or [])
    return found


def validate_doc(
    doc: Any,
    allowed_attachments: set[str] | None = None,
    allowed_tickmarks: set[str] | None = None,
) -> None:
    """Refuse tout nœud, marque, lien ou image non admis.

    Les images doivent désigner une pièce jointe du papier (`attachment:<id>`) ; les liens
    pointent vers le web, une adresse e-mail ou un autre papier de l'application.
    """
    if not is_valid_doc(doc):
        raise InvalidDocument("Contenu des travaux invalide")
    stack = [doc]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            raise InvalidDocument("Contenu des travaux invalide")
        kind = node.get("type")
        if kind not in ALLOWED_NODES:
            raise InvalidDocument(f"Élément non admis dans les travaux : {kind}")
        for mark in node.get("marks", []) or []:
            if mark.get("type") not in ALLOWED_MARKS:
                raise InvalidDocument(f"Mise en forme non admise : {mark.get('type')}")
            if mark["type"] == "link":
                href = str((mark.get("attrs") or {}).get("href", ""))
                if not href.startswith(LINK_PREFIXES):
                    raise InvalidDocument("Lien non admis : web, e-mail ou papier de travail")
        if kind == "image":
            src = str((node.get("attrs") or {}).get("src", ""))
            if not src.startswith(IMAGE_PREFIX):
                raise InvalidDocument("Une image doit être une pièce jointe du papier")
            if (
                allowed_attachments is not None
                and src[len(IMAGE_PREFIX) :] not in allowed_attachments
            ):
                raise InvalidDocument("Image inconnue : déposez-la d'abord en pièce jointe")
        if kind == "tickmark" and allowed_tickmarks is not None:
            if str((node.get("attrs") or {}).get("id", "")) not in allowed_tickmarks:
                raise InvalidDocument("Marque de révision inconnue")
        stack.extend(node.get("content", []) or [])
