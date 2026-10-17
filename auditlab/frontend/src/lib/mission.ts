import type { EngagementStatus } from "../api/types";

export const STATUSES: EngagementStatus[] = [
  "planifiee",
  "preparation",
  "terrain",
  "revue",
  "rapport",
  "cloturee",
];

export const STATUS_BADGE: Record<EngagementStatus, string> = {
  planifiee: "bg-slate-200 text-slate-800",
  preparation: "bg-sky-100 text-sky-900",
  terrain: "bg-indigo-100 text-indigo-900",
  revue: "bg-amber-100 text-amber-900",
  rapport: "bg-purple-100 text-purple-900",
  cloturee: "bg-green-100 text-green-900",
};

/** Part du budget consommée, bornée à 100 % pour la barre ; le dépassement est signalé à part. */
export function budgetRatio(consumed: number, budget: number): number {
  if (budget <= 0) return 0;
  return Math.min(consumed / budget, 1);
}
