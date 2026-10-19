import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { ClosingSummary } from "../../api/portfolio";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

export const STAGES = ["pieces", "saisie", "revision", "revue", "depot", "termine"] as const;
interface Deadline { code: string; libelle: string; echeance: string; periode: string; client?: string; client_id?: string }
interface Board {
  dossiers: { client_id: string; client: string; cloture: ClosingSummary | null; avancement: number; prochaine_echeance: Deadline | null; echeances_en_retard: number; en_retard: boolean; documents_expires: number }[];
  par_etape: Record<string, number>;
  echeances_a_venir: Deadline[];
  dossiers_en_retard: string[];
  horizon_jours: number;
}

/** Tableau de bord du portefeuille (RCO-02). */
export default function PortfolioDashboard() {
  const { t } = useTranslation();
  const [b, setB] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Board>("/portfolio/dashboard").then(setB).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!b || b.dossiers.length === 0) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="carte space-y-3 lg:col-span-2" aria-labelledby="tb-avancement">
        <h2 id="tb-avancement" className="text-base font-semibold">{t("tableauPortefeuille.avancement")}</h2>
        <ul className="flex flex-wrap gap-2 text-xs">
          {STAGES.map((s) => <li key={s} className="rounded bg-slate-100 px-2 py-1">{t(`portefeuille.etapes.${s}`)} : {b.par_etape[s]}</li>)}
        </ul>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["dossier", "etape", "prochaine", "retard"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`tableauPortefeuille.${k}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {b.dossiers.map((d) => (
              <tr key={d.client_id} className={d.en_retard ? "bg-red-50" : ""}>
                <th scope="row" className="py-1 pr-3 font-normal"><Link className="text-marque-700 underline" to={`/portefeuille/${d.client_id}`}>{d.client}</Link></th>
                <td className="py-1 pr-3">
                  {d.cloture ? (
                    <div className="flex items-center gap-2">
                      <span className="w-20">{d.cloture.exercice} · {t(`portefeuille.etapes.${d.cloture.etape}`)}</span>
                      <progress max={100} value={d.avancement} aria-label={t("tableauPortefeuille.avancementDe", { client: d.client })} className="h-2 w-24" />
                    </div>
                  ) : "—"}
                </td>
                <td className="py-1 pr-3">{d.prochaine_echeance ? `${formatDate(d.prochaine_echeance.echeance)} · ${d.prochaine_echeance.libelle}` : "—"}</td>
                <td className="py-1 pr-3">
                  {d.en_retard ? <span className="font-medium text-red-700">{t("tableauPortefeuille.enRetard", { count: d.echeances_en_retard })}</span> : "—"}
                  {d.documents_expires > 0 && <span className="ml-2 text-xs text-red-700">{t("tableauPortefeuille.documentsExpires", { count: d.documents_expires })}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="carte space-y-2" aria-labelledby="tb-echeances">
        <h2 id="tb-echeances" className="text-base font-semibold">{t("tableauPortefeuille.aVenir", { jours: b.horizon_jours })}</h2>
        {b.echeances_a_venir.length === 0 ? <p className="text-sm text-slate-600">{t("calendrier.aucune")}</p> : (
          <ul className="space-y-1 text-sm">
            {b.echeances_a_venir.map((d) => (
              <li key={`${d.client_id}-${d.code}-${d.echeance}`}>{formatDate(d.echeance)} · {d.client} · {d.libelle} ({d.periode})</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
