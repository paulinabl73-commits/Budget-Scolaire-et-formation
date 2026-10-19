import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import DashboardFilters, {
  EMPTY_FILTER,
} from "../components/dashboards/DashboardFilters";
import type { DashboardFilter } from "../components/dashboards/DashboardFilters";
import DirectionDashboard from "../components/dashboards/DirectionDashboard";
import RecommendationsDashboard from "../components/dashboards/RecommendationsDashboard";

const TABS = ["direction", "recommandations"] as const;

/** Tableaux de bord de la Direction de l'audit (REP-04, REP-05, REP-08). */
export default function DashboardsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("vue") ?? "")
    ? (params.get("vue") as (typeof TABS)[number])
    : TABS[0];
  const [filter, setFilter] = useState<DashboardFilter>(EMPTY_FILTER);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("tableauxDeBord.titre")}</h1>
      <nav
        aria-label={t("tableauxDeBord.titre")}
        className="flex gap-1 border-b border-slate-200"
      >
        {TABS.map((k) => (
          <button
            key={k}
            type="button"
            aria-current={k === tab ? "page" : undefined}
            onClick={() => setParams({ vue: k })}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${k === tab ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600"}`}
          >
            {t(`tableauxDeBord.vues.${k}`)}
          </button>
        ))}
      </nav>
      <DashboardFilters
        value={filter}
        onChange={setFilter}
        criticite={tab === "recommandations"}
      />
      {tab === "direction" && <DirectionDashboard filter={filter} />}
      {tab === "recommandations" && (
        <RecommendationsDashboard filter={filter} />
      )}
    </div>
  );
}
