import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { formatNombre } from "../../lib/format";
import ExcelExport from "./ExcelExport";
import Kpi, { Bar } from "./Kpi";

interface MissionBoard {
  papiers: {
    total: number;
    par_etat: Record<string, number>;
    taux_approbation: number;
    liste: {
      id: string;
      reference: string;
      titre: string;
      etat: string;
      notes_ouvertes: number;
    }[];
  };
  notes_ouvertes: number;
  temps: {
    budget_jours: number;
    jours_consommes: number;
    taux_consommation: number;
    par_personne: { nom: string; jours: number }[];
    par_activite: { activite: string; jours: number }[];
  };
  constats_par_statut: Record<string, number>;
}

/** Tableau de bord d'une mission (REP-06). */
export default function MissionDashboard({ missionId }: { missionId: string }) {
  const { t } = useTranslation();
  const [data, setData] = useState<MissionBoard | null>(null);
  useEffect(() => {
    api<MissionBoard>(`/dashboards/missions/${missionId}`).then(setData, () =>
      setData(null),
    );
  }, [missionId]);
  if (!data) return null;
  const maxPerson = Math.max(...data.temps.par_personne.map((p) => p.jours), 1);
  return (
    <section className="space-y-3" aria-labelledby="tb-mission">
      <h2 id="tb-mission" className="text-base font-semibold">
        {t("tableauxDeBord.mission.titre")}
      </h2>
      <div className="flex justify-end">
        <ExcelExport
          path={`/dashboards/missions/${missionId}/export`}
          filename={"tableau_mission.xlsx"}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <Kpi
          label={t("tableauxDeBord.mission.papiers")}
          value={`${data.papiers.taux_approbation} %`}
          detail={t("tableauxDeBord.mission.papiersDetail", {
            approuves: data.papiers.par_etat.approuve,
            total: data.papiers.total,
          })}
        />
        <Kpi
          label={t("tableauxDeBord.mission.notes")}
          value={String(data.notes_ouvertes)}
        />
        <Kpi
          label={t("tableauxDeBord.mission.temps")}
          value={`${formatNombre(data.temps.jours_consommes)} / ${formatNombre(data.temps.budget_jours)} j`}
          detail={t("tableauxDeBord.direction.consommation", {
            taux: data.temps.taux_consommation,
          })}
        />
        <Kpi
          label={t("tableauxDeBord.mission.constats")}
          value={String(
            Object.values(data.constats_par_statut).reduce((a, b) => a + b, 0),
          )}
          detail={t("tableauxDeBord.mission.valides", {
            n: data.constats_par_statut.valide ?? 0,
          })}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="carte space-y-2">
          <h3 className="font-medium">{t("tableauxDeBord.mission.etats")}</h3>
          {Object.entries(data.papiers.par_etat).map(([s, n]) => (
            <Bar
              key={s}
              label={t(`tableauxDeBord.mission.etatsPapier.${s}`)}
              value={n}
              max={Math.max(data.papiers.total, 1)}
            />
          ))}
          <ul className="text-sm">
            {data.papiers.liste
              .filter((w) => w.notes_ouvertes > 0)
              .map((w) => (
                <li key={w.id}>
                  <Link
                    to={`/missions/${missionId}/papiers/${w.id}`}
                    className="text-marque-700 underline"
                  >
                    {w.reference}
                  </Link>{" "}
                  :{" "}
                  {t("tableauxDeBord.mission.notesPapier", {
                    n: w.notes_ouvertes,
                  })}
                </li>
              ))}
          </ul>
        </div>
        <div className="carte space-y-2">
          <h3 className="font-medium">
            {t("tableauxDeBord.mission.parPersonne")}
          </h3>
          {data.temps.par_personne.length === 0 && (
            <p className="text-sm text-slate-600">—</p>
          )}
          {data.temps.par_personne.map((p) => (
            <Bar key={p.nom} label={p.nom} value={p.jours} max={maxPerson} />
          ))}
        </div>
      </div>
    </section>
  );
}
