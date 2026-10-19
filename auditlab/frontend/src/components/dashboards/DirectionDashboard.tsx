import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";
import type { DashboardFilter } from "./DashboardFilters";
import { toQuery } from "./DashboardFilters";
import Kpi, { Bar } from "./Kpi";

interface Direction {
  plan: {
    annee: number;
    version: number;
    missions_prevues: number;
    missions_lancees: number;
    missions_cloturees: number;
    taux_realisation: number;
    budget_jours: number;
  } | null;
  missions_par_statut: Record<string, number>;
  budget_jours: number;
  jours_consommes: number;
  taux_consommation: number;
  missions: {
    id: string;
    reference: string;
    titre: string;
    entite: string | null;
    statut: string;
    budget_jours: number;
    jours_consommes: number;
    ecart_jours: number;
  }[];
}

/** Tableau de bord Direction (REP-04). */
export default function DirectionDashboard({
  filter,
}: {
  filter: DashboardFilter;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<Direction | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Direction>(`/dashboards/direction${toQuery(filter)}`).then(
      setData,
      (e: Error) => setError(e.message),
    );
  }, [filter]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const max = Math.max(...Object.values(data.missions_par_statut), 1);
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Kpi
          label={t("tableauxDeBord.direction.plan")}
          value={data.plan ? `${data.plan.taux_realisation} %` : "—"}
          detail={
            data.plan
              ? t("tableauxDeBord.direction.planDetail", data.plan)
              : t("tableauxDeBord.direction.sansPlan")
          }
        />
        <Kpi
          label={t("tableauxDeBord.direction.missions")}
          value={String(data.missions.length)}
        />
        <Kpi
          label={t("tableauxDeBord.direction.jours")}
          value={`${formatNombre(data.jours_consommes)} / ${formatNombre(data.budget_jours)}`}
          detail={t("tableauxDeBord.direction.consommation", {
            taux: data.taux_consommation,
          })}
        />
        <Kpi
          label={t("tableauxDeBord.direction.ecart")}
          value={formatNombre(
            Math.round((data.budget_jours - data.jours_consommes) * 100) / 100,
          )}
        />
      </div>
      <section className="carte space-y-2" aria-labelledby="tb-statuts">
        <h2 id="tb-statuts" className="text-base font-semibold">
          {t("tableauxDeBord.direction.parStatut")}
        </h2>
        {Object.entries(data.missions_par_statut).map(([s, n]) => (
          <Bar key={s} label={t(`missions.statuts.${s}`)} value={n} max={max} />
        ))}
      </section>
      <section
        className="carte overflow-x-auto p-0"
        aria-labelledby="tb-missions"
      >
        <h2 id="tb-missions" className="px-4 pt-4 text-base font-semibold">
          {t("tableauxDeBord.direction.budget")}
        </h2>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              {[
                "mission",
                "entite",
                "statut",
                "budget",
                "consommes",
                "ecart",
              ].map((k) => (
                <th key={k} scope="col" className="px-4 py-2">
                  {t(`tableauxDeBord.col.${k}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {data.missions.map((m) => (
              <tr key={m.id}>
                <td className="px-4 py-2">
                  <Link
                    to={`/missions/${m.id}`}
                    className="text-marque-700 underline"
                  >
                    {m.reference}
                  </Link>{" "}
                  {m.titre}
                </td>
                <td className="px-4 py-2">{m.entite ?? "—"}</td>
                <td className="px-4 py-2">
                  {t(`missions.statuts.${m.statut}`)}
                </td>
                <td className="px-4 py-2 text-right">
                  {formatNombre(m.budget_jours)}
                </td>
                <td className="px-4 py-2 text-right">
                  {formatNombre(m.jours_consommes)}
                </td>
                <td
                  className={`px-4 py-2 text-right ${m.ecart_jours < 0 ? "text-red-700" : ""}`}
                >
                  {formatNombre(m.ecart_jours)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
