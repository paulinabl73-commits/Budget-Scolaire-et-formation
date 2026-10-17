import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Engagement } from "../api/types";
import Alert from "../components/Alert";
import DataTab from "../components/mission/DataTab";
import FindingsTab from "../components/mission/FindingsTab";
import RevisionTab from "../components/mission/RevisionTab";
import ProgramTab from "../components/mission/ProgramTab";
import StatusBar from "../components/mission/StatusBar";
import StatusHistory from "../components/mission/StatusHistory";
import SynthesisTab from "../components/mission/SynthesisTab";
import TimeTab from "../components/mission/TimeTab";
import WorkpapersTab from "../components/mission/WorkpapersTab";
import { formatDate, formatDateHeure } from "../lib/format";
import { STATUS_BADGE } from "../lib/mission";

/** Onglets de la fiche mission ; chaque lot ajoute les siens. */
export const MISSION_TABS = ["synthese", "programme", "papiers", "donnees", "constats", "revision", "temps"] as const;
type Tab = (typeof MISSION_TABS)[number];

export default function MissionPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const tab = (MISSION_TABS as readonly string[]).includes(params.get("onglet") ?? "")
    ? (params.get("onglet") as Tab)
    : "synthese";
  const [mission, setMission] = useState<Engagement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const created = (location.state as { created?: string } | null)?.created;

  const load = useCallback(async () => {
    setMission(await api<Engagement>(`/engagements/${id}`));
  }, [id]);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!mission) return <p>{t("commun.chargement")}</p>;

  return (
    <div className="space-y-6">
      <Link to="/missions" className="text-sm text-marque-700 underline">{t("missions.retour")}</Link>
      {created && <Alert kind="succes">{t("missions.creee", { reference: created })}</Alert>}
      <header className="space-y-1">
        <p className="font-mono text-sm text-slate-600">{mission.reference}</p>
        <h1 className="text-2xl font-semibold">
          {mission.titre}{" "}
          <span className={`ml-1 rounded-full px-2 py-0.5 align-middle text-xs font-medium ${STATUS_BADGE[mission.statut]}`}>
            {t(`missions.statuts.${mission.statut}`)}
          </span>
        </h1>
        <p className="text-sm text-slate-600">
          {formatDate(mission.date_debut)} – {formatDate(mission.date_fin)}
          {mission.entity_nom && ` · ${mission.entity_nom}`}
          {mission.chef_nom && ` · ${t("missions.chef")} : ${mission.chef_nom}`}
        </p>
        {!mission.peut_gerer && <p className="text-sm text-slate-600">{t("missions.lectureSeule")}</p>}
      </header>
      {mission.cloturee_le && (
        <Alert kind="info">{t("missions.clotureeLe", { date: formatDateHeure(mission.cloturee_le) })}</Alert>
      )}
      <StatusBar mission={mission} onChange={setMission} />
      <nav aria-label={t("missions.titre")} className="flex gap-1 border-b border-slate-200">
        {MISSION_TABS.map((k) => (
          <button
            key={k}
            type="button"
            aria-current={k === tab ? "page" : undefined}
            onClick={() => setParams({ onglet: k })}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              k === tab ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t(`missions.onglets.${k}`)}
          </button>
        ))}
      </nav>
      {tab === "synthese" && (
        <>
          <SynthesisTab mission={mission} onChange={setMission} />
          <StatusHistory missionId={mission.id} statut={mission.statut} />
        </>
      )}
      {tab === "programme" && <ProgramTab mission={mission} />}
      {tab === "papiers" && <WorkpapersTab mission={mission} />}
      {tab === "donnees" && <DataTab mission={mission} />}
      {tab === "constats" && <FindingsTab mission={mission} />}
      {tab === "revision" && <RevisionTab mission={mission} />}
      {tab === "temps" && <TimeTab mission={mission} onChange={() => void load()} />}
    </div>
  );
}
