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
