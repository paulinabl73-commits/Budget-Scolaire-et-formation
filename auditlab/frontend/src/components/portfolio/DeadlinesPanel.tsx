import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

interface Deadline { rule_id: string; code: string; libelle: string; nature: string; periode: string; echeance: string; fait_le: string | null; statut: "fait" | "en_retard" | "a_venir"; jours_restants: number }
const BADGE = { fait: "bg-emerald-50 text-emerald-800", en_retard: "bg-red-50 text-red-800", a_venir: "bg-slate-100 text-slate-700" };

/** Échéances fiscales et sociales d'un client (RCO-03). */
export default function DeadlinesPanel({ clientId, canWork }: { clientId: string; canWork: boolean }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Deadline[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Deadline[]>(`/clients/${clientId}/deadlines`).then(setItems), [clientId]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const toggle = async (d: Deadline) => {
    setError(null);
    try {
      await put(`/clients/${clientId}/deadlines/${d.rule_id}/${d.echeance}`, { fait: d.statut !== "fait" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="carte space-y-2" aria-labelledby="cl-echeances">
      <h2 id="cl-echeances" className="text-base font-semibold">{t("calendrier.echeances")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {items && (items.length === 0 ? <p className="text-sm text-slate-600">{t("calendrier.aucune")}</p> : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["echeance", "obligation", "periode", "statut"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`calendrier.${k}`)}</th>)}<th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((d) => (
              <tr key={`${d.rule_id}-${d.echeance}`}>
                <td className="py-1 pr-3">{formatDate(d.echeance)}</td>
                <th scope="row" className="py-1 pr-3 font-normal">{d.libelle} <span className="text-xs text-slate-500">({t(`calendrier.natures.${d.nature}`)})</span></th>
                <td className="py-1 pr-3">{d.periode}</td>
                <td className="py-1 pr-3"><span className={`rounded px-2 py-0.5 text-xs ${BADGE[d.statut]}`}>{t(`calendrier.statuts.${d.statut}`)}{d.fait_le && ` ${formatDate(d.fait_le)}`}</span></td>
                <td className="py-1">{canWork && <button type="button" className="underline" onClick={() => void toggle(d)}>{d.statut === "fait" ? t("calendrier.rouvrir") : t("calendrier.marquerFait")}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </section>
  );
}
