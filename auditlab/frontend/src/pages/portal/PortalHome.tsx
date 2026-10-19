import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { Criticality } from "../../api/types";
import Alert from "../../components/Alert";
import CriticalityBadge from "../../components/finding/CriticalityBadge";
import { formatDate } from "../../lib/format";
import PortalPieces from "./PortalPieces";

export interface PortalFinding {
  id: string;
  reference: string;
  titre: string;
  criticite: Criticality;
  statut: "envoye" | "repondu" | "valide";
  date_limite_reponse: string | null;
  mission: { reference: string; titre: string };
  peut_repondre: boolean;
  plans_ouverts: number;
  plans_en_retard: number;
}

/** Portail audité (CON-09) : uniquement ses constats et plans d'action. */
export default function PortalHome({ nom }: { nom: string }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<PortalFinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<PortalFinding[]>("/portal/findings").then(setRows).catch((e: Error) => setError(e.message));
  }, []);
  const toAnswer = rows?.filter((f) => f.peut_repondre) ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("portail.titre", { nom })}</h1>
        <p className="text-slate-600">{t("portail.intro")}</p>
      </header>
      {error && <Alert kind="erreur">{error}</Alert>}
      {toAnswer.length > 0 && (
        <Alert kind="info">{t("portail.aRepondre", { n: toAnswer.length })}</Alert>
      )}
      <PortalPieces />
      <section className="carte overflow-x-auto p-0" aria-labelledby="portail-liste">
        <h2 id="portail-liste" className="px-4 pt-4 text-lg font-semibold">{t("portail.mesConstats")}</h2>
        {rows && rows.length === 0 ? (
          <p className="p-4 text-sm text-slate-600">{t("portail.aucun")}</p>
        ) : (
          <table className="mt-2 w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {["mission", "constat", "criticite", "etat", "plans"].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">{t(`portail.col.${k}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {(rows ?? []).map((f) => (
                <tr key={f.id}>
                  <td className="px-4 py-2">{f.mission.reference} · {f.mission.titre}</td>
                  <td className="px-4 py-2">
                    <Link className="text-marque-700 underline" to={`/portail/constats/${f.id}`}>{f.reference} · {f.titre}</Link>
                  </td>
                  <td className="px-4 py-2"><CriticalityBadge value={f.criticite} /></td>
                  <td className="px-4 py-2">
                    {f.peut_repondre ? t("portail.repondreAvant", { date: formatDate(f.date_limite_reponse) }) : t(`portail.etats.${f.statut}`)}
                  </td>
                  <td className="px-4 py-2">
                    {t("portail.plansOuverts", { n: f.plans_ouverts })}
                    {f.plans_en_retard > 0 && <span className="ml-2 rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">{t("portail.enRetard", { n: f.plans_en_retard })}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
