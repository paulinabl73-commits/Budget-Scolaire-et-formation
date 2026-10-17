import { fromPlainText, toPlainText } from "../lib/richtext";

describe("documents riches", () => {
  it("convertit texte et document dans les deux sens", () => {
    const doc = fromPlainText("Ligne 1\n\nLigne 2");
    expect(doc.content).toHaveLength(2);
    expect(toPlainText(doc as never)).toBe("Ligne 1\nLigne 2");
  });

  it("rend tableaux, listes et tickmarks comme le serveur", () => {
    const doc = {
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "Total " }, { type: "tickmark", attrs: { symbole: "Σ" } }] },
        { type: "table", content: [{ type: "tableRow", content: [
          { type: "tableCell", content: [{ type: "paragraph", content: [{ type: "text", text: "A" }] }] },
          { type: "tableCell", content: [{ type: "paragraph", content: [{ type: "text", text: "B" }] }] },
        ] }] },
        { type: "bulletList", content: [{ type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "point" }] }] }] },
      ],
    };
    expect(toPlainText(doc)).toBe("Total [Σ]\nA\tB\n- point");
  });
});

describe("images des papiers", () => {
  it("affiche les pièces jointes par lien signé et n'enregistre que leur référence", async () => {
    const { resolveImages, unresolveImages } = await import("../lib/richtext");
    const stored = {
      type: "doc" as const,
      content: [{ type: "paragraph", content: [{ type: "image", attrs: { src: "attachment:42", alt: "pièce" } }] }],
    };
    const shown = resolveImages(stored, { "42": "/api/attachments/42/content?sig=x" });
    const img = (shown.content as { content: { attrs: Record<string, unknown> }[] }[])[0].content[0];
    expect(img.attrs).toEqual({ src: "/api/attachments/42/content?sig=x", alt: "pièce", attachmentId: "42" });
    expect(unresolveImages(shown)).toEqual(stored);
  });
});
