import type { PlanItem } from "../api/types";

export type DiffField = "titre" | "budget_jours" | "periode_debut" | "periode_fin";
const FIELDS: DiffField[] = ["titre", "budget_jours", "periode_debut", "periode_fin"];

export type PlanDiff =
  | { kind: "ajoutee"; item: PlanItem }
  | { kind: "retiree"; item: PlanItem }
  | { kind: "modifiee"; item: PlanItem; changes: { field: DiffField; before: unknown; after: unknown }[] };

/** Différences entre deux versions d'un plan, rapprochées par entité (AUD-05). */
export function diffPlans(previous: PlanItem[], current: PlanItem[]): PlanDiff[] {
  const before = new Map(previous.map((i) => [i.entity_id, i]));
  const after = new Map(current.map((i) => [i.entity_id, i]));
  const result: PlanDiff[] = [];
  for (const item of current) {
    const old = before.get(item.entity_id);
    if (!old) {
      result.push({ kind: "ajoutee", item });
      continue;
    }
    const changes = FIELDS.filter((f) => old[f] !== item[f]).map((field) => ({
      field,
      before: old[field],
      after: item[field],
    }));
    if (changes.length) result.push({ kind: "modifiee", item, changes });
  }
  for (const item of previous) {
    if (!after.has(item.entity_id)) result.push({ kind: "retiree", item });
  }
  return result;
}
