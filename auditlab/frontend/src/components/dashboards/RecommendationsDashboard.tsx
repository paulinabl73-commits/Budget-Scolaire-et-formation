import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";
import type { DashboardFilter } from "./DashboardFilters";
import { toQuery } from "./DashboardFilters";
import Kpi, { Bar } from "./Kpi";

interface Recommendations {
  constats_par_criticite: Record<string, number>;
  plans_par_criticite_et_statut: Record<string, Record<string, number>>;
  plans: number;
  taux_mise_en_oeuvre: number;
  taux_mise_en_oeuvre_echus: number;
  retards_par_direction: {
    direction: string;
    plans_en_retard: number;
    plus_ancienne_echeance: string;
  }[];
  plans_en_retard: {
    id: string;
    constat: string;
    mission: string;
    criticite: string;
    description: string;
    responsable: string | null;
    echeance: string;
    jours_de_retard: number;
    direction: string;
  }[];
}

const STATUTS = [
  "a_lancer",
  "en_cours",
  "realise",
  "verifie",
  "risque_accepte",
];

/** Tableau de bord Recommandations (REP-05). */
export default function RecommendationsDashboard({
  filter,
}: {
  filter: DashboardFilter;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<Recommendations | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Recommendations>(`/dashboards/recommendations${toQuery(filter)}`).then(
      setData,
      (e: Error) => setError(e.message),
    );
  }, [filter]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const total = Object.values(data.constats_par_criticite).reduce(
    (a, b) => a + b,
    0,
  );
  const maxLate = Math.max(
    ...data.retards_par_direction.map((d) => d.plans_en_retard),
    1,
  );
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Kpi
          label={t("tableauxDeBord.reco.recommandations")}
          value={String(total)}
          detail={t("tableauxDeBord.reco.plans", { n: data.plans })}
        />
        <Kpi
          label={t("tableauxDeBord.reco.taux")}
          value={`${data.taux_mise_en_oeuvre} %`}
        />
        <Kpi
          label={t("tableauxDeBord.reco.tauxEchus")}
          value={`${data.taux_mise_en_oeuvre_echus} %`}
        />
        <Kpi
          label={t("tableauxDeBord.reco.retards")}
          value={String(data.plans_en_retard.length)}
        />
      </div>
      <section className="carte overflow-x-auto" aria-labelledby="tb-matrice">
        <h2 id="tb-matrice" className="text-base font-semibold">
          {t("tableauxDeBord.reco.matrice")}
        </h2>
        <table className="mt-2 w-full text-sm">
          <thead>
            <tr className="text-left">
              <th scope="col">{t("tableauxDeBord.criticite")}</th>
              <th scope="col" className="text-right">
                {t("tableauxDeBord.reco.constats")}
              </th>
              {STATUTS.map((s) => (
                <th key={s} scope="col" className="text-right">
                  {t(`plans.statuts.${s}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.plans_par_criticite_et_statut).map(
              ([c, row]) => (
                <tr key={c} className="border-t">
                  <th scope="row" className="text-left font-normal">
                    {t(`constats.criticites.${c}`)}
                  </th>
                  <td className="text-right">
                    {data.constats_par_criticite[c]}
                  </td>
                  {STATUTS.map((s) => (
                    <td key={s} className="text-right">
                      {row[s]}
                    </td>
                  ))}
                </tr>
              ),
            )}
          </tbody>
        </table>
      </section>
      <section className="carte space-y-2" aria-labelledby="tb-retards">
        <h2 id="tb-retards" className="text-base font-semibold">
          {t("tableauxDeBord.reco.parDirection")}
        </h2>
        {data.retards_par_direction.length === 0 && (
          <p className="text-sm text-slate-600">
            {t("tableauxDeBord.reco.aucunRetard")}
          </p>
        )}
        {data.retards_par_direction.map((d) => (
          <Bar
            key={d.direction}
            label={d.direction}
            value={d.plans_en_retard}
            max={maxLate}
          />
        ))}
      </section>
      {data.plans_en_retard.length > 0 && (
        <section
          className="carte overflow-x-auto p-0"
          aria-labelledby="tb-liste-retards"
        >
          <h2
            id="tb-liste-retards"
            className="px-4 pt-4 text-base font-semibold"
          >
            {t("tableauxDeBord.reco.liste")}
          </h2>
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {[
                  "constat",
                  "direction",
                  "plan",
                  "responsable",
                  "echeance",
                  "retard",
                ].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">
                    {t(`tableauxDeBord.reco.col.${k}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {data.plans_en_retard.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-2">
                    {p.mission} · {p.constat} (
                    {t(`constats.criticites.${p.criticite}`)})
                  </td>
                  <td className="px-4 py-2">{p.direction}</td>
                  <td className="px-4 py-2">{p.description}</td>
                  <td className="px-4 py-2">{p.responsable ?? "—"}</td>
                  <td className="px-4 py-2">{formatDate(p.echeance)}</td>
                  <td className="px-4 py-2 text-right text-red-700">
                    {t("tableauxDeBord.reco.jours", { n: p.jours_de_retard })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
