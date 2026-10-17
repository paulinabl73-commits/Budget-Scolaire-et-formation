import { mergeAttributes, Node } from "@tiptap/core";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    tickmark: {
      insertTickmark: (attrs: { id: string; symbole: string; couleur: string; libelle: string }) => ReturnType;
    };
  }
}

/** Marque de révision (AUD-16) : nœud insécable, en ligne, dans le texte et les tableaux. */
export const TickmarkNode = Node.create({
  name: "tickmark",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      id: { default: null },
      symbole: { default: "✓" },
      couleur: { default: "#1f5fa8" },
      libelle: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-tickmark]" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-tickmark": node.attrs.id,
        title: node.attrs.libelle,
        "aria-label": `Marque : ${node.attrs.libelle}`,
        class: "tickmark",
        style: `color:${node.attrs.couleur}`,
      }),
      node.attrs.symbole,
    ];
  },

  renderText({ node }) {
    return `[${node.attrs.symbole}]`;
  },

  addCommands() {
    return {
      insertTickmark:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),
    };
  },
});
