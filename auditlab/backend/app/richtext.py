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
