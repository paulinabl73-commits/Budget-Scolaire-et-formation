import type { RichDoc } from "../api/types";

type Node = { type?: string; text?: string; content?: Node[]; attrs?: Record<string, unknown> };

/** Miroir de app/richtext.py : texte brut d'un document riche. */
export function toPlainText(input: Node | RichDoc | null | undefined): string {
  const node = input as Node | null | undefined;
  if (!node) return "";
  if (node.type === "text") return node.text ?? "";
  if (node.type === "tickmark") return `[${String(node.attrs?.symbole ?? "")}]`;
  if (node.type === "hardBreak") return "\n";
  const children = (node.content ?? []).map(toPlainText);
  if (["doc", "bulletList", "orderedList", "table"].includes(node.type ?? "")) {
    return children.filter((c) => c !== "").join("\n");
  }
  if (node.type === "tableRow") return children.join("\t");
  if (node.type === "listItem") return `- ${children.join("\n")}`;
  return children.join("");
}

export function fromPlainText(text: string): RichDoc {
  return {
    type: "doc",
    content: text
      .split("\n")
      .filter((l) => l.trim())
      .map((l) => ({ type: "paragraph", content: [{ type: "text", text: l }] })),
  };
}

type AnyNode = { type?: string; attrs?: Record<string, unknown>; content?: AnyNode[]; [k: string]: unknown };

function mapImages(node: AnyNode, fn: (attrs: Record<string, unknown>) => Record<string, unknown>): AnyNode {
  const next: AnyNode = { ...node };
  if (node.type === "image" && node.attrs) next.attrs = fn(node.attrs);
  if (node.content) next.content = node.content.map((c) => mapImages(c, fn));
  return next;
}

/** Remplace les références « attachment:<id> » par des liens signés affichables. */
export function resolveImages(doc: RichDoc, urls: Record<string, string>): RichDoc {
  return mapImages(doc as AnyNode, (attrs) => {
    const src = String(attrs.src ?? "");
    if (!src.startsWith("attachment:")) return attrs;
    const id = src.slice("attachment:".length);
    return { ...attrs, attachmentId: id, src: urls[id] ?? "" };
  }) as RichDoc;
}

/** Inverse de resolveImages avant enregistrement : seules les références sont stockées. */
export function unresolveImages(doc: RichDoc): RichDoc {
  return mapImages(doc as AnyNode, (attrs) => {
    const { attachmentId, ...rest } = attrs;
    return attachmentId ? { ...rest, src: `attachment:${String(attachmentId)}` } : rest;
  }) as RichDoc;
}
