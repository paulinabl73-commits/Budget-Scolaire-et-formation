import { useTranslation } from "react-i18next";

import type { Plan } from "../api/types";
import { formatDate, formatNombre } from "../lib/format";
import { diffPlans } from "../lib/planDiff";
import type { DiffField } from "../lib/planDiff";

const BADGES = {
  ajoutee: "bg-green-100 text-green-900",
  retiree: "bg-red-100 text-red-900",
  modifiee: "bg-amber-100 text-amber-900",
} as const;

function show(field: DiffField, value: unknown): string {
  if (field === "budget_jours") return `${formatNombre(Number(value))} j`;
  if (field === "periode_debut" || field === "periode_fin") return formatDate(String(value));
  return String(value);
}

export default function PlanComparison({ previous, current }: { previous: Plan; current: Plan }) {
  const { t } = useTranslation();
  const diffs = diffPlans(previous.items, current.items);
  return (
    <div className="space-y-2 rounded-md border border-slate-200 p-4">
      <h3 className="text-base font-semibold">{t("plan.comparaison", { version: previous.version })}</h3>
      {diffs.length === 0 ? (
        <p className="text-sm text-slate-600">{t("plan.aucuneDifference")}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {diffs.map((d) => (
            <li key={`${d.kind}-${d.item.id}`}>
              <span className={`mr-2 rounded px-2 py-0.5 text-xs font-medium ${BADGES[d.kind]}`}>
                {t(`plan.${d.kind}`)}
              </span>
              <span className="font-medium">{d.item.titre}</span>
              {d.kind === "modifiee" && (
                <span className="text-slate-600">
                  {" — "}
                  {d.changes
                    .map((c) => `${t(`plan.champs.${c.field}`)} : ${show(c.field, c.before)} → ${show(c.field, c.after)}`)
                    .join(" ; ")}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
