import type { PlanItem } from "../api/types";
import { diffPlans } from "../lib/planDiff";

const item = (entity: string, extra: Partial<PlanItem> = {}): PlanItem => ({
  id: `${entity}-${Math.random()}`,
  entity_id: entity,
  entity_nom: entity,
  score_risque: null,
  titre: `Audit ${entity}`,
  budget_jours: 20,
  periode_debut: "2027-02-01",
  periode_fin: "2027-03-15",
  justification: null,
  ...extra,
});

describe("comparaison de versions du plan", () => {
  it("détecte ajouts, retraits et modifications", () => {
    const v1 = [item("achats"), item("paie"), item("tresorerie")];
    const v2 = [item("achats", { budget_jours: 25 }), item("paie"), item("stocks")];
    const diffs = diffPlans(v1, v2);
    expect(diffs.map((d) => [d.kind, d.item.entity_id])).toEqual([
      ["modifiee", "achats"],
      ["ajoutee", "stocks"],
      ["retiree", "tresorerie"],
    ]);
    const modif = diffs[0];
    expect(modif.kind === "modifiee" && modif.changes).toEqual([
      { field: "budget_jours", before: 20, after: 25 },
    ]);
  });

  it("ne signale rien pour deux versions identiques", () => {
    expect(diffPlans([item("a")], [item("a")])).toEqual([]);
  });
});
