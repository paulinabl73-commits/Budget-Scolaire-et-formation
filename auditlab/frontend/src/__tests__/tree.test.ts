import { buildTree, descendantIds } from "../lib/tree";
import { formatDate } from "../lib/format";

const items = [
  { id: "b", parent_id: "a", nom: "Ventes" },
  { id: "a", parent_id: null, nom: "Direction commerciale" },
  { id: "c", parent_id: "a", nom: "Achats" },
  { id: "d", parent_id: "c", nom: "ERP" },
  { id: "e", parent_id: null, nom: "Comptabilité" },
];

describe("arborescence de l'univers", () => {
  it("construit et trie l'arbre par nom", () => {
    const tree = buildTree(items);
    expect(tree.map((n) => n.item.nom)).toEqual(["Comptabilité", "Direction commerciale"]);
    expect(tree[1].children.map((n) => n.item.nom)).toEqual(["Achats", "Ventes"]);
    expect(tree[1].children[0].children[0].item.id).toBe("d");
  });

  it("liste une entité et ses descendants", () => {
    expect([...descendantIds(items, "a")].sort()).toEqual(["a", "b", "c", "d"]);
    expect([...descendantIds(items, "e")]).toEqual(["e"]);
  });

  it("formate une date seule", () => {
    expect(formatDate("2024-03-31")).toBe("31/03/2024");
    expect(formatDate(null)).toBe("");
  });
});

describe("évaluation des risques", () => {
  it("calcule la note d'ancienneté comme le serveur", async () => {
    const { seniorityNote } = await import("../lib/risk");
    expect(seniorityNote(null, "2027-01-01")).toBe(5);
    expect(seniorityNote("2026-06-01", "2027-01-01")).toBe(1);
    expect(seniorityNote("2025-01-02", "2027-01-01")).toBe(2);
    expect(seniorityNote("2025-01-01", "2027-01-01")).toBe(3);
    expect(seniorityNote("2010-01-01", "2027-01-01")).toBe(5);
  });
});

describe("carte des risques", () => {
  it("classe les cases par niveau", async () => {
    const { cellLevel } = await import("../lib/risk");
    expect(cellLevel(1, 1)).toBe("faible");
    expect(cellLevel(2, 2)).toBe("modere");
    expect(cellLevel(4, 2)).toBe("eleve");
    expect(cellLevel(5, 3)).toBe("critique");
  });
});
