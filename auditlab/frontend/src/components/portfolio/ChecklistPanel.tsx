import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import Alert from "../Alert";

interface Point { code: string; libelle: string; statut: "fait" | "sans_objet" | "anomalie" | null; commentaire: string | null }
interface Checklist { cycles: { cycle: string; libelle: string; points: Point[] }[]; total: number; traites: number; anomalies: number; avancement: number }
const STATUTS = ["fait", "sans_objet", "anomalie"] as const;

/** Check-lists de révision par cycle d'une clôture (RCO-07). */
export default function ChecklistPanel({ closingId }: { closingId: string }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Checklist | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/closings/${closingId}/checklist`;
  const load = useCallback(() => api<Checklist>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const save = async (p: Point, statut: Point["statut"], commentaire: string | null) => {
    setError(null);
    try {
      setData(await put<Checklist>(`${url}/${p.code}`, { statut, commentaire }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby={`ck-${closingId}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`ck-${closingId}`} className="text-base font-semibold">{t("checklistRevision.titre")}</h2>
        <span className="text-sm text-slate-600">{t("checklistRevision.avancement", { traites: data.traites, total: data.total, anomalies: data.anomalies })}</span>
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      {data.cycles.map((c) => (
        <details key={c.cycle} className="rounded border border-slate-200 p-2">
          <summary className="cursor-pointer text-sm font-medium">{c.libelle} ({c.points.filter((p) => p.statut).length}/{c.points.length})</summary>
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {c.points.map((p) => (
              <li key={p.code} className="flex flex-wrap items-center gap-2 py-1">
                <span className="min-w-64 flex-1"><span className="font-mono text-xs text-slate-500">{p.code}</span> {p.libelle}</span>
                <select aria-label={t("checklistRevision.statutDe", { code: p.code })} className="rounded border px-1 py-0.5" value={p.statut ?? ""}
                  onChange={(e) => {
                    const statut = (e.target.value || null) as Point["statut"];
                    const comment = statut === "anomalie" ? window.prompt(t("checklistRevision.commentaire"), p.commentaire ?? "") : p.commentaire;
                    if (statut === "anomalie" && !comment) return;
                    void save(p, statut, comment ?? null);
                  }}>
                  <option value="">—</option>
                  {STATUTS.map((s) => <option key={s} value={s}>{t(`checklistRevision.statuts.${s}`)}</option>)}
                </select>
                {p.commentaire && <span className={`w-full text-xs ${p.statut === "anomalie" ? "text-red-700" : "text-slate-500"}`}>{p.commentaire}</span>}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </section>
  );
}
